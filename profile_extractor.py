"""
Profile Extractor — uses a local LLM to build and maintain contact profiles.
Converted to Async with Pydantic for high-performance extraction.
"""

import asyncio
import json
import logging
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

## Task
1. Analyze the messages below to extract facts about the **Sender** OR **anyone else** they mention.
2. For each fact, identify the **Subject** (the person the fact is about).
3. Identify if the information is coming from the person themselves (**First-party**) or a third party.

## Category Guide
- **Identity**: Full name, nicknames, family role.
- **Biographical**: Birthday, age, location, education.
- **Professional**: Work, company, role, skills.
- **Interests**: Hobbies, favorite things, frequent topics.
- **Social**: Relationships (e.g., "John is the brother"), nicknames for others.

## Output Format
Respond ONLY with a valid JSON object.
{{
  "extractions": [
    {{
      "subject_name": "Name of the person this fact is about (use 'Self' for the sender)",
      "category": "Work|Location|Family|Interest|Preference|Other",
      "value": "The specific fact",
      "confidence": "high|medium|low",
      "source_quote": "Exact snippet from the text",
      "is_first_party": true/false (true if the subject is speaking about themselves)
    }}
  ],
  "summary_of_sender": "A 1-2 sentence overview of the sender specifically."
}}
"""

class ProfileExtractor:
    """
    Reads the raw message log, groups by contact, and uses Ollama
    to extract structured personal facts using async parallelism.
    """

    def __init__(self):
        self._ollama_url = config.OLLAMA_BASE_URL
        self._model = config.OLLAMA_MODEL
        self._profiles: dict[str, ContactProfile] = self._load_profiles()
        self._processed_line_count = self._get_processed_count()
        self._semaphore = asyncio.Semaphore(5) # Throttle Ollama calls to 5 concurrent tasks

    def _load_profiles(self) -> dict[str, ContactProfile]:
        """Load existing contact profiles from disk."""
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

    def _save_profiles(self):
        """Persist contact profiles to disk."""
        data = {
            "contacts": {
                cid: profile.model_dump() for cid, profile in self._profiles.items()
            },
            "last_extraction": datetime.now(timezone.utc).isoformat(),
            "total_contacts": len(self._profiles),
            "processed_lines": self._processed_line_count
        }
        with open(config.CONTACTS_FILE, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _get_processed_count(self) -> int:
        """Check how many log lines have already been processed."""
        if config.CONTACTS_FILE.exists():
            with open(config.CONTACTS_FILE) as f:
                try:
                    data = json.load(f)
                    return data.get("processed_lines", 0)
                except Exception:
                    return 0
        return 0

    async def extract_profiles(self, force_all: bool = False) -> int:
        """
        Process messages and extract facts for ANY subject mentioned (Async).
        """
        if not config.RAW_LOG_FILE.exists():
            logger.warning("No message log found. Run a sync first.")
            return 0

        messages_by_sender: dict[str, list[dict[str, Any]]] = {}
        current_line = 0

        with open(config.RAW_LOG_FILE) as f:
            for i, line in enumerate(f):
                current_line = i + 1
                if not force_all and current_line <= self._processed_line_count:
                    continue

                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                sender_key = record.get("sender_id", record.get("sender_name", "unknown"))
                if sender_key not in messages_by_sender:
                    messages_by_sender[sender_key] = []
                messages_by_sender[sender_key].append(record)

        if not messages_by_sender:
            logger.info("No new messages to process")
            self._processed_line_count = current_line
            self._save_profiles()
            return 0

        logger.info(f"Planning extraction for {len(messages_by_sender)} senders...")
        
        tasks = []
        for sender_id, messages in messages_by_sender.items():
            sender_name = messages[0].get("sender_name", sender_id)
            meaningful = [m for m in messages if len(m.get("text", "")) > 5]
            if not meaningful:
                continue
            
            # Process large histories in chunks
            chunk_size = 50
            for i in range(0, len(meaningful), chunk_size):
                chunk = meaningful[i:i + chunk_size]
                tasks.append(self._process_chunk(sender_name, sender_id, chunk))

        logger.info(f"Created {len(tasks)} extraction tasks. Executing asynchronously...")
        
        # Run all tasks with semaphore throttling
        results = await asyncio.gather(*tasks)
        
        contacts_updated_set = set()
        for res in results:
            if not res: continue
            
            sender_id = res["sender_id"]
            sender_name = res["sender_name"]
            extraction_result: ExtractionResult = res["result"]
            
            sender_profile = self._get_or_create_profile(sender_id, sender_name)
            if extraction_result.summary_of_sender:
                sender_profile.summary = extraction_result.summary_of_sender

            for fact in extraction_result.extractions:
                subj_name = fact.subject_name
                
                target_profile = None
                if subj_name.lower() == "self" or subj_name.lower() == sender_name.lower():
                    target_profile = sender_profile
                    fact.is_first_party = True
                else:
                    target_profile = self.get_profile(subj_name)
                    if not target_profile:
                        target_profile = self._get_or_create_profile(subj_name, subj_name)
                    fact.is_first_party = False
                
                target_profile.add_fact(fact)
                target_profile.message_count += 1
                contacts_updated_set.add(target_profile.contact_id)

        self._processed_line_count = current_line
        self._save_profiles()
        return len(contacts_updated_set)

    async def _process_chunk(self, sender_name: str, sender_id: str, chunk: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Process a single chunk of messages through Ollama."""
        async with self._semaphore:
            result = await self._extract_facts_async(sender_name, sender_id, chunk)
            if result:
                return {
                    "sender_name": sender_name,
                    "sender_id": sender_id,
                    "result": result
                }
            return None

    def _get_or_create_profile(self, contact_id: str, display_name: str) -> ContactProfile:
        if contact_id not in self._profiles:
            self._profiles[contact_id] = ContactProfile(contact_id=contact_id, display_name=display_name)
        return self._profiles[contact_id]

    async def _extract_facts_async(
        self, 
        sender_name: str, 
        sender_id: str,
        messages: list[dict[str, Any]]
    ) -> ExtractionResult | None:
        """Send a batch of messages to Ollama asynchronously."""
        formatted_messages = []
        for msg in messages:
            ts = msg.get("timestamp", "")[:16]
            text = msg.get("text", "")
            formatted_messages.append(f"[{ts}] {text}")

        prompt = EXTRACTION_PROMPT.format(
            sender_name=sender_name,
            sender_id=sender_id,
            messages="\n".join(formatted_messages),
        )

        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = await self._call_ollama_async(prompt)
                if not response:
                    continue

                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                if json_start == -1 or json_end == 0:
                    continue

                data = json.loads(response[json_start:json_end])
                return ExtractionResult.model_validate(data)
            except Exception:
                continue
                    
        return None

    async def _call_ollama_async(self, prompt: str) -> str:
        """Call Ollama's generate endpoint asynchronously."""
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
