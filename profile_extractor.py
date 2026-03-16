import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
import httpx
from pydantic import ValidationError
import config
from models import ContactProfile, ExtractionResult, Fact

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
You are an expert personal intelligence analyst. Your goal is to build a rich, accurate, and non-redundant profile of contacts based on chat history.

## Context
Sender: **{sender_name}** ({sender_id})
Messages:
{messages_block}

## Task & Instructions
1. **Analyze Context:** Read the chat history carefully. Track the flow of conversation to resolve pronouns (who "he", "she", or "they" refers to).
2. **Decode Slang & Infer:** Translate slang, shorthand, or emojis into formal, concrete facts. Use strong contextual inference.
3. **Extract Facts:** Identify concrete, meaningful facts about the Sender OR anyone else mentioned. 
4. **Determine Source:** Identify if the information is first-party (Self) or third-party.

## Category Guide
- **Identity**: Full name, aliases, family role.
- **Biographical**: Birthday, age, location, education, life events.
- **Professional**: Work, company, role, skills, projects.
- **Interest**: Hobbies, favorite things.
- **Social**: Relationships (e.g., "John is the brother").

## CRITICAL RULES
- **THINK FIRST:** Use the "reasoning_scratchpad" to analyze context BEFORE outputting facts.
- **NO FILLERS:** DO NOT output facts with values like "Unknown".
- **EXACT NAMES:** Use actual names or "{sender_name}".
- **JSON ONLY:** Output nothing but valid JSON.

## Output Format
{{
  "reasoning_scratchpad": "Brief analysis and slang decoding.",
  "summary_of_sender": "1-2 sentence overview.",
  "extractions": [
    {{
      "subject_name": "Actual Name",
      "category": "Identity|Biographical|Professional|Interest|Social",
      "value": "The fact",
      "confidence": "high|medium|low",
      "source_quote": "Snippet",
      "is_first_party": true
    }}
  ]
}}
"""

class ProfileExtractor:
    def __init__(self):
        self._ollama_url = config.OLLAMA_BASE_URL
        self._model = config.OLLAMA_MODEL
        self._profiles: dict[str, ContactProfile] = self._load_profiles()
        self._processed_line_count = self._get_processed_count()
        # Use config or default to 2 for safety with 14B
        concurrency = getattr(config, "EXTRACTION_CONCURRENCY", 2)
        self._semaphore = asyncio.Semaphore(concurrency) 

    def _load_profiles(self) -> dict[str, ContactProfile]:
        profiles: dict[str, ContactProfile] = {}
        if config.CONTACTS_FILE.exists():
            try:
                with open(config.CONTACTS_FILE) as f:
                    data = json.load(f)
                    for contact_id, profile_data in data.get("contacts", {}).items():
                        try:
                            profiles[contact_id] = ContactProfile.model_validate(profile_data)
                        except ValidationError as e:
                            logger.warning(f"Failed to validate profile for {contact_id}: {e}")
            except Exception as e:
                logger.error(f"Failed to load contacts file: {e}")
        logger.info(f"Loaded {len(profiles)} existing contact profiles")
        return profiles

    def _save_profiles(self, processed_lines: int):
        data = {
            "contacts": {
                cid: profile.model_dump() for cid, profile in self._profiles.items()
            },
            "last_extraction": datetime.now(timezone.utc).isoformat(),
            "total_contacts": len(self._profiles),
            "processed_lines": processed_lines
        }
        temp_file = config.CONTACTS_FILE.with_suffix(".tmp")
        try:
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_file.replace(config.CONTACTS_FILE)
        except Exception as e:
            logger.error(f"Failed to save profiles: {e}")

    def _get_processed_count(self) -> int:
        if config.CONTACTS_FILE.exists():
            with open(config.CONTACTS_FILE) as f:
                try:
                    data = json.load(f)
                    return data.get("processed_lines", 0)
                except Exception:
                    return 0
        return 0

    async def extract_profiles(self, force_all: bool = False) -> int:
        if not config.RAW_LOG_FILE.exists():
            logger.warning("No message log found. Run a sync first.")
            return 0

        messages_by_chat: dict[str, list[dict[str, Any]]] = {}
        current_line = 0
        
        logger.info("Scanning message log...")
        with open(config.RAW_LOG_FILE) as f:
            for i, line in enumerate(f):
                current_line = i + 1
                if not force_all and current_line <= self._processed_line_count:
                    continue

                line = line.strip()
                if not line: continue
                try:
                    record = json.loads(line)
                    chat_id = record.get("chat_id", "unknown")
                    if chat_id not in messages_by_chat:
                        messages_by_chat[chat_id] = []
                    messages_by_chat[chat_id].append(record)
                except json.JSONDecodeError:
                    continue

        if not messages_by_chat:
            logger.info("No new messages to process")
            self._processed_line_count = current_line
            self._save_profiles(current_line)
            return 0

        all_tasks_metadata = []
        chunk_size = getattr(config, "EXTRACTION_BATCH_SIZE", 50)
        
        for chat_id, messages in messages_by_chat.items():
            meaningful = [m for m in messages if len(m.get("text", "")) > 3]
            if not meaningful: continue
            
            other_participants = list(set(
                m.get("sender_name") for m in meaningful 
                if m.get("sender_name") and m.get("sender_name") != config.MY_NAME
            ))
            other_name = other_participants[0] if other_participants else "Unknown"
            chat_name = meaningful[0].get("chat_name", other_name)

            for i in range(0, len(meaningful), chunk_size):
                chunk = meaningful[i:i + chunk_size]
                all_tasks_metadata.append({
                    "sender_name": chat_name,
                    "sender_id": chat_id,
                    "chunk": chunk
                })

        total_tasks = len(all_tasks_metadata)
        logger.info(f"Starting {total_tasks} extraction tasks incrementally...")
        
        contacts_updated_set = set()
        completed_count = 0
        
        async def process_task(metadata):
            async with self._semaphore:
                res = await self._extract_facts_async(
                    metadata["sender_name"], 
                    metadata["sender_id"], 
                    metadata["chunk"]
                )
                return metadata, res

        # Process as they complete
        pending = [asyncio.ensure_future(process_task(m)) for m in all_tasks_metadata]
        
        for future in asyncio.as_completed(pending):
            metadata, result = await future
            completed_count += 1
            
            if result:
                extraction_result: ExtractionResult = result
                partner_id = metadata["sender_id"]
                partner_name = metadata["sender_name"]
                
                if extraction_result.summary_of_sender:
                    partner_profile = self._get_or_create_profile(partner_id, partner_name)
                    partner_profile.summary = extraction_result.summary_of_sender

                for fact in extraction_result.extractions:
                    subj_name = fact.subject_name
                    if not subj_name: continue
                    
                    target_profile = None
                    if subj_name.lower() in ["self", config.MY_NAME.lower(), "{sender_name}".lower()]:
                        target_profile = self._get_or_create_profile(config.MY_NAME, config.MY_NAME)
                        fact.is_first_party = True
                    else:
                        target_profile = self.get_profile(subj_name)
                        if not target_profile:
                            target_profile = self._get_or_create_profile(subj_name, subj_name)
                    
                    target_profile.add_fact(fact)
                    target_profile.message_count += 1
                    contacts_updated_set.add(target_profile.contact_id)

            # Log progress every 5 tasks and save every 10
            if completed_count % 5 == 0 or completed_count == total_tasks:
                progress = (completed_count / total_tasks) * 100
                logger.info(f"Progress: {progress:.2f}% ({completed_count}/{total_tasks}) | {len(contacts_updated_set)} contacts updated")
            
            if completed_count % 10 == 0:
                self._save_profiles(self._processed_line_count)

        self._processed_line_count = current_line
        self._save_profiles(current_line)
        return len(contacts_updated_set)

    def _get_or_create_profile(self, contact_id: str, display_name: str) -> ContactProfile:
        if contact_id not in self._profiles:
            self._profiles[contact_id] = ContactProfile(contact_id=contact_id, display_name=display_name)
        return self._profiles[contact_id]

    async def _extract_facts_async(self, sender_name: str, sender_id: str, messages: list[dict[str, Any]]) -> ExtractionResult | None:
        formatted_messages = []
        for msg in messages:
            ts = msg.get("timestamp", "")[:16]
            sender = msg.get("sender_name", "Unknown")
            text = msg.get("text", "")
            formatted_messages.append(f"[{ts}] {sender}: {text}")

        prompt = EXTRACTION_PROMPT.format(
            sender_name=sender_name,
            sender_id=sender_id,
            messages_block="\n".join(formatted_messages),
        )

        for attempt in range(2):
            try:
                response = await self._call_ollama_async(prompt)
                if not response: continue
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                if json_start == -1 or json_end == 0: continue
                data = json.loads(response[json_start:json_end])
                return ExtractionResult.model_validate(data)
            except Exception:
                continue
        return None

    async def _call_ollama_async(self, prompt: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    f"{self._ollama_url}/api/generate",
                    json={
                        "model": self._model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {
                            "temperature": 0.1,
                            "num_predict": 1024, 
                            "num_ctx": 4096      
                        },
                    },
                )
                resp.raise_for_status()
                return resp.json().get("response", "")
        except Exception as e:
            logger.error(f"Async Ollama call failed: {e}")
            return ""

    def get_all_profiles(self) -> dict[str, ContactProfile]:
        return self._profiles

    def get_profile(self, contact_name: str) -> ContactProfile | None:
        query = contact_name.lower()
        for profile in self._profiles.values():
            if query in profile.display_name.lower():
                return profile
        return None
