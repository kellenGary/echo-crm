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
from storage import DataStore

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
You are an expert personal intelligence analyst. Your goal is to build a rich, accurate, and non-redundant profile of contacts based on chat history.

## Context
Current Date: {current_date}
User (You): **{my_name}**
Primary Contact (The person you are talking to): **{sender_name}** ({sender_id})

## Chat History
{messages_block}

## Task & Instructions
1. **Analyze Context & Time:** Read the chat history carefully. Use the [YYYY-MM-DD HH:MM] timestamps for each message.
   - If a message mentions "yesterday", "tomorrow", or "next week", use the message's timestamp to determine the actual date.
   - Facts should be anchored in time if possible (e.g., "Visited Japan in June 2024").
2. **Distinguish Senders (CRITICAL):**
    - Messages from **{my_name}** are YOUR messages.
    - Messages from **{sender_name}** are the CONTACT's messages.
    - **SENDER IDENTIFICATION:** The name at the start of each message line (e.g. `[{my_name}]: ...`) is the person who SPOKE those words. 
    - If a person says "I work at...", that fact applies to the SENDER of that message.
    - DO NOT attribute facts about {my_name} to {sender_name} or vice-versa. 
    - When extracting a fact about the Primary Contact, use their name "**{sender_name}**" as the subject_name.
    - When extracting a fact about yourself, use "**{my_name}**" as the subject_name.
3. **Decode Slang & Infer:** Translate slang, shorthand, or emojis into formal, concrete facts. Use strong contextual inference.
4. **Extract Facts:** Identify concrete, meaningful facts about the Primary Contact, Yourself, or anyone else mentioned. 
5. **Determine Source:** Identify if the information is first-party (Self - the person spoke it about themselves) or third-party (someone else spoke it about them).

## Category Guide
- **Identity**: Full name, aliases, family role.
- **Biographical**: Birthday, age, location, education, life events.
- **Professional**: Work, company, role, skills, projects.
- **Interest**: Hobbies, favorite things.
- **Social**: Relationships (e.g., "John is the brother").

## CRITICAL RULES
- **THINK FIRST:** Use the "reasoning_scratchpad" to analyze context and timestamps BEFORE outputting facts.
- **NO MIXING:** Be extremely careful to attribute facts to the correct person. 
- **FIRST-PERSON PRONOUNS:** If {my_name} says "I am a doctor", then {my_name} is the doctor. If {sender_name} says "I am a doctor", then {sender_name} is the doctor.
- **JSON ONLY:** Output nothing but valid JSON.

## Output Format
{{
  "reasoning_scratchpad": "Brief analysis of conversation flow, timestamp resolution, and slang decoding.",
  "summary_of_sender": "1-2 sentence overview of the Primary Contact ({sender_name}) only.",
  "extractions": [
    {{
      "subject_name": "Actual Name (e.g. {sender_name} or {my_name})",
      "category": "Identity|Biographical|Professional|Interest|Social",
      "value": "The fact (include temporal context if available)",
      "confidence": "high|medium|low",
      "source_quote": "Snippet",
      "is_first_party": true
    }}
  ],
  "relationships": [
    {{
      "target_name": "Person/Place Name",
      "type": "friend|family|colleague|works_at|lives_in",
      "context": "Brief context including dates if mentioned",
      "confidence": "high|medium|low"
    }}
  ]
}}
"""

class ProfileExtractor:
    def __init__(self):
        self._ollama_url = config.OLLAMA_BASE_URL
        self._model = config.OLLAMA_MODEL
        self._store = DataStore(config.DATA_DIR / "echo_nosql.json")
        self._profiles: dict[str, ContactProfile] = self._store.get_all_profiles()
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
        # Save to NoSQL Store
        for profile in self._profiles.values():
            self._store.save_profile(profile)

        # Run Fact Resolver Analytic
        discoveries = self._store.get_shared_intelligence()

        data = {
            "contacts": {
                cid: profile.model_dump() for cid, profile in self._profiles.items()
            },
            "discoveries": discoveries, 
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

        total_updated = 0
        batch_size_lines = 500 
        current_batch_lines = []
        current_line_num = 0
        
        logger.info(f"Starting extraction from line {self._processed_line_count}...")

        with open(config.RAW_LOG_FILE, "r") as f:
            for i, line in enumerate(f):
                current_line_num = i + 1
                
                # Skip already processed lines unless forced
                if not force_all and current_line_num <= self._processed_line_count:
                    continue
                
                current_batch_lines.append(line)
                
                # Process batch when it reaches the limit
                if len(current_batch_lines) >= batch_size_lines:
                    logger.info(f"--- Processing Batch (Lines {current_line_num - batch_size_lines + 1} to {current_line_num}) ---")
                    batch_updated = await self._process_line_batch(current_batch_lines)
                    total_updated += batch_updated
                    
                    # Update checkpoint
                    self._processed_line_count = current_line_num
                    self._save_profiles(current_line_num)
                    current_batch_lines = []
            
            # Process remaining lines
            if current_batch_lines:
                logger.info(f"--- Processing Final Batch (Lines up to {current_line_num}) ---")
                batch_updated = await self._process_line_batch(current_batch_lines)
                total_updated += batch_updated
                self._processed_line_count = current_line_num
                self._save_profiles(current_line_num)

        return total_updated

    async def _process_line_batch(self, lines: list[str]) -> int:
        """Process a specific subset of lines and return number of updated contacts."""
        messages_by_chat: dict[str, list[dict[str, Any]]] = {}
        for line in lines:
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
            return 0

        all_tasks_metadata = []
        chunk_size = getattr(config, "EXTRACTION_BATCH_SIZE", 50)
        
        for chat_id, messages in messages_by_chat.items():
            meaningful = [m for m in messages if len(m.get("text", "")) > 3]
            if not meaningful: continue
            
            other_participants = list(set(
                m.get("sender_name") for m in meaningful 
                if m.get("sender_name") and not m.get("is_self", False)
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
        if total_tasks == 0:
            return 0

        logger.info(f"  Batch Tasks: {total_tasks} chunks")
        
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
                    if subj_name.lower() in ["self", config.MY_NAME.lower()]:
                        target_profile = self._get_or_create_profile(config.MY_NAME, config.MY_NAME)
                        fact.is_first_party = True
                    elif subj_name.lower() == partner_name.lower():
                        target_profile = self._get_or_create_profile(partner_id, partner_name)
                    else:
                        target_profile = self.get_profile(subj_name)
                        if not target_profile:
                            target_profile = self._get_or_create_profile(subj_name, subj_name)
                    
                    if target_profile:
                        target_profile.add_fact(fact)
                        target_profile.message_count += 1
                        contacts_updated_set.add(target_profile.contact_id)

                for rel in extraction_result.relationships:
                    partner_profile = self._get_or_create_profile(partner_id, partner_name)
                    partner_profile.add_relationship(rel)
                    contacts_updated_set.add(partner_profile.contact_id)

            # Progress log for the current batch
            if completed_count % 10 == 0 or completed_count == total_tasks:
                progress = (completed_count / total_tasks) * 100
                logger.debug(f"  Batch Progress: {progress:.1f}% ({completed_count}/{total_tasks})")

        return len(contacts_updated_set)

    def _get_or_create_profile(self, contact_id: str, display_name: str) -> ContactProfile:
        if contact_id not in self._profiles:
            self._profiles[contact_id] = ContactProfile(contact_id=contact_id, display_name=display_name)
        return self._profiles[contact_id]

    async def _extract_facts_async(self, sender_name: str, sender_id: str, messages: list[dict[str, Any]]) -> ExtractionResult | None:
        formatted_messages = []
        for msg in messages:
            ts = msg.get("timestamp", "")[:16]
            is_self = msg.get("is_self", False)
            
            # Use the EXACT names passed into the prompt context to avoid any naming ambiguity for the model
            sender_label = config.MY_NAME if is_self else sender_name
            
            text = msg.get("text", "")
            formatted_messages.append(f"[{ts}] {sender_label}: {text}")

        prompt = EXTRACTION_PROMPT.format(
            current_date=datetime.now().strftime("%Y-%m-%d"),
            my_name=config.MY_NAME,
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
