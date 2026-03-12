"""
Profile Extractor — uses a local LLM to build and maintain contact profiles.

Responsibilities:
  - Read new messages from the JSONL log
  - Group messages by contact (sender)
  - Send batches to Ollama to extract structured personal facts
  - Merge extracted facts into a persistent contacts.json knowledge base

The extracted profiles serve as a fast lookup for the query engine,
while the raw log remains available for deeper context searches.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

import config

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
You are an information extraction assistant. Given a batch of chat messages \
from a specific person, extract any personal facts you can find.

Focus on extracting these categories (only include what's actually mentioned):
- **Full name** (if mentioned or inferable)
- **Birthday** or age
- **Where they work** / job title / company
- **Where they live** / city / state
- **School or university**
- **Interests or hobbies**
- **Relationships** (spouse, kids, family mentioned)
- **Important dates** (anniversaries, events)
- **Preferences** (food, music, etc.)
- **Other notable facts**

Respond ONLY with a valid JSON object using this schema:
{{
  "facts": [
    {{
      "category": "<category name>",
      "value": "<the fact>",
      "confidence": "<high|medium|low>",
      "source_quote": "<brief quote from message>"
    }}
  ]
}}

If no personal facts are found, return: {{"facts": []}}

---
Messages from **{contact_name}**:

{messages}
"""


class ContactProfile:
    """Represents accumulated knowledge about a single contact."""

    def __init__(self, contact_id: str, display_name: str):
        self.contact_id = contact_id
        self.display_name = display_name
        self.facts: list[dict[str, Any]] = []
        self.last_updated: str = ""
        self.message_count: int = 0

    def add_facts(self, new_facts: list[dict[str, Any]]):
        """Merge new facts, avoiding exact duplicates, and update name if found."""
        existing_values = {(f["category"], f["value"]) for f in self.facts}
        for fact in new_facts:
            key = (fact.get("category", ""), fact.get("value", ""))
            
            # If the LLM extracted a Full name for someone with a phone number name
            if key[0].lower() == "full name" and fact.get("confidence") in ["medium", "high"]:
                val = key[1].strip()
                # Skip false positives and defaults
                if (val.lower() not in ["not mentioned", "not available", "not inferable", "unknown", "none", "", "not specified"] 
                    and "'" not in val 
                    and self.display_name.startswith("+")): 
                    self.display_name = val

            if key not in existing_values:
                self.facts.append(fact)
                existing_values.add(key)
        self.last_updated = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "contact_id": self.contact_id,
            "display_name": self.display_name,
            "facts": self.facts,
            "last_updated": self.last_updated,
            "message_count": self.message_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContactProfile":
        profile = cls(data["contact_id"], data["display_name"])
        profile.facts = data.get("facts", [])
        profile.last_updated = data.get("last_updated", "")
        profile.message_count = data.get("message_count", 0)
        return profile


class ProfileExtractor:
    """
    Reads the raw message log, groups by contact, and uses Ollama
    to extract structured personal facts into contact profiles.
    """

    def __init__(self):
        self._ollama_url = config.OLLAMA_BASE_URL
        self._model = config.OLLAMA_MODEL
        self._profiles: dict[str, ContactProfile] = self._load_profiles()
        self._processed_line_count = self._get_processed_count()

    def _load_profiles(self) -> dict[str, ContactProfile]:
        """Load existing contact profiles from disk."""
        profiles: dict[str, ContactProfile] = {}
        if config.CONTACTS_FILE.exists():
            with open(config.CONTACTS_FILE) as f:
                data = json.load(f)
                for contact_id, profile_data in data.get("contacts", {}).items():
                    profiles[contact_id] = ContactProfile.from_dict(profile_data)
        logger.info(f"Loaded {len(profiles)} existing contact profiles")
        return profiles

    def _save_profiles(self):
        """Persist contact profiles to disk."""
        data = {
            "contacts": {
                cid: profile.to_dict() for cid, profile in self._profiles.items()
            },
            "last_extraction": datetime.now(timezone.utc).isoformat(),
            "total_contacts": len(self._profiles),
        }
        with open(config.CONTACTS_FILE, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _get_processed_count(self) -> int:
        """Check how many log lines have already been processed."""
        # Store this in the contacts file metadata
        if config.CONTACTS_FILE.exists():
            with open(config.CONTACTS_FILE) as f:
                data = json.load(f)
                return data.get("processed_lines", 0)
        return 0

    def _save_processed_count(self, count: int):
        """Update processed line count in contacts file."""
        if config.CONTACTS_FILE.exists():
            with open(config.CONTACTS_FILE) as f:
                data = json.load(f)
        else:
            data = {}
        data["processed_lines"] = count
        data["contacts"] = {
            cid: profile.to_dict() for cid, profile in self._profiles.items()
        }
        data["last_extraction"] = datetime.now(timezone.utc).isoformat()
        data["total_contacts"] = len(self._profiles)
        with open(config.CONTACTS_FILE, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def extract_profiles(self) -> int:
        """
        Process new messages from the log and extract contact facts.
        Returns the number of contacts updated.
        """
        if not config.RAW_LOG_FILE.exists():
            logger.warning("No message log found. Run a sync first.")
            return 0

        # Read only new lines from the log
        messages_by_contact: dict[str, list[dict[str, Any]]] = {}
        current_line = 0

        with open(config.RAW_LOG_FILE) as f:
            for i, line in enumerate(f):
                current_line = i + 1
                if current_line <= self._processed_line_count:
                    continue

                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Skip our own messages — we want info about OTHER people
                if record.get("is_self", False):
                    continue

                # Group by sender_name (which resolves to Mac address book) so text + beeper msgs merge
                sender_name = record.get("sender_name", record.get("sender_id", "unknown"))
                if sender_name not in messages_by_contact:
                    messages_by_contact[sender_name] = []
                messages_by_contact[sender_name].append(record)

        if not messages_by_contact:
            logger.info("No new messages to process for profile extraction")
            self._save_processed_count(current_line)
            return 0

        logger.info(
            f"Processing messages from {len(messages_by_contact)} contacts"
        )

        contacts_updated = 0
        for sender_id, messages in messages_by_contact.items():
            if len(messages) < 2:
                # Need a reasonable amount of messages for extraction
                continue

            contact_name = messages[0].get("sender_name", "Unknown")
            logger.info(
                f"  Extracting facts for {contact_name} "
                f"({len(messages)} messages)..."
            )

            try:
                chunk_size = 200
                facts = []
                
                # Filter meaningless very short messages first to vastly speed up historical LLM scans
                meaningful_messages = [m for m in messages if len(m.get("text", "")) > 5]
                
                for i in range(0, len(meaningful_messages), chunk_size):
                    chunk = meaningful_messages[i:i + chunk_size]
                    if len(chunk) < 2:
                        continue
                    if len(meaningful_messages) > chunk_size:
                        logger.info(f"    -> Processing chunk {i//chunk_size + 1}/{(len(meaningful_messages) + chunk_size - 1)//chunk_size}...")
                        
                    chunk_facts = self._extract_facts(contact_name, chunk)
                    if chunk_facts:
                        facts.extend(chunk_facts)
                
                if facts:
                    profile = self._profiles.get(sender_id)
                    if not profile:
                        profile = ContactProfile(sender_id, contact_name)
                        self._profiles[sender_id] = profile

                    profile.add_facts(facts)
                    profile.message_count += len(messages)
                    contacts_updated += 1
                    logger.info(
                        f"    → Extracted {len(facts)} facts for {contact_name}"
                    )
            except Exception as e:
                logger.error(f"    → Failed extraction for {contact_name}: {e}")

        self._save_processed_count(current_line)
        logger.info(f"Profile extraction complete: {contacts_updated} contacts updated")
        return contacts_updated

    def _extract_facts(
        self, contact_name: str, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Send a batch of messages to Ollama for fact extraction."""
        # Format messages for the prompt
        formatted_messages = []
        for msg in messages:
            ts = msg.get("timestamp", "")
            text = msg.get("text", "")
            chat = msg.get("chat_name", "")
            formatted_messages.append(f"[{ts}] (in chat: {chat}) {text}")

        base_prompt = EXTRACTION_PROMPT.format(
            contact_name=contact_name,
            messages="\n".join(formatted_messages),
        )

        prompt = base_prompt
        max_retries = 2
        
        for attempt in range(max_retries):
            # Call Ollama
            response = self._call_ollama(prompt)
            if not response:
                break

            # Parse JSON from response
            try:
                # Try to find JSON in the response
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                if json_start == -1 or json_end == 0:
                    raise ValueError("No JSON object found in response")

                result = json.loads(response[json_start:json_end])
                return result.get("facts", [])
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse LLM response as JSON for {contact_name} on attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    prompt = base_prompt + f"\n\nERROR: The previous response was invalid JSON: {str(e)}. Please try again and return ONLY valid JSON. Make sure to properly escape quotes within strings (using \\\"), remove any trailing commas, and preserve the original message quotes perfectly."
                else:
                    logger.error(f"Giving up on {contact_name} after {max_retries} attempts.")
                    
        return []

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama's generate endpoint."""
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    f"{self._ollama_url}/api/generate",
                    json={
                        "model": self._model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {
                            "temperature": 0.1,  # Low temp for factual extraction
                            "num_predict": 1024,
                        },
                    },
                )
                resp.raise_for_status()
                return resp.json().get("response", "")
        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            return ""

    def get_all_profiles(self) -> dict[str, ContactProfile]:
        """Return all contact profiles."""
        return self._profiles

    def get_profile(self, contact_name: str) -> ContactProfile | None:
        """Find a profile by display name (case-insensitive partial match)."""
        query = contact_name.lower()
        for profile in self._profiles.values():
            if query in profile.display_name.lower():
                return profile
        return None
