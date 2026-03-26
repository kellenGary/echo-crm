import asyncio
import json
import logging
import os
from filelock import FileLock
from datetime import datetime, timezone
from typing import Any
from pydantic import ValidationError
import config
from gemini_client import GeminiClient
from models import ContactProfile, ExtractionResult, Fact, GroupChatSummary
from storage import DataStore

logger = logging.getLogger(__name__)

# JSON schema for Gemini structured output — matches ExtractionResult
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning_scratchpad": {"type": "string"},
        "summary_of_sender": {"type": "string"},
        "extractions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject_name": {"type": "string"},
                    "category": {"type": "string"},
                    "value": {"type": "string"},
                    "confidence": {"type": "string"},
                    "source_quote": {"type": "string"},
                    "is_first_party": {"type": "boolean"},
                    "temporal_status": {"type": "string"},
                },
                "required": ["subject_name", "category", "value", "confidence", "source_quote", "is_first_party", "temporal_status"],
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string"},
                    "type": {"type": "string"},
                    "context": {"type": "string"},
                    "confidence": {"type": "string"},
                },
                "required": ["target_name", "type", "context", "confidence"],
            },
        },
    },
    "required": ["reasoning_scratchpad", "summary_of_sender", "extractions", "relationships"],
}

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

## Temporal Status (CRITICAL)
For each fact, determine whether it is **still true today** ({current_date}):
- `"current"` — The fact is clearly still true (e.g., "I live in Columbus" said recently).
- `"past"` — The fact was true at the time but is likely no longer true. **Use past tense** in the value field. For example, if someone said "I am sick" 2 years ago, write the value as "Was sick (March 2024)" not "Is sick".
- `"unknown"` — Cannot determine if the fact is still true.

**Rule of thumb**: If a message is more than 6 months old relative to {current_date}, strongly consider whether the fact is still current or should be marked as "past" with past-tense phrasing. Temporary states (sick, traveling, studying for an exam) should almost always be "past" unless very recent.

## Relationship Rules (CRITICAL)
- **DO NOT assume strong relationship types from a single mention.** If a person's name is mentioned once in passing, use type `"knows"` with `"medium"` or `"low"` confidence.
- **Strong types** like `"family"`, `"significant_other"`, or `"brother"` require EXPLICIT statements (e.g., "he's my brother", "she's my girlfriend") — not inference.
- Use ONE of these types only: `friend`, `family`, `colleague`, `knows`, `works_at`, `lives_in`. Do NOT combine types with pipes (e.g., do NOT write "friend|colleague").
- Set confidence to `"high"` ONLY when there are multiple messages corroborating the relationship, or an explicit statement.

## CRITICAL RULES
- **THINK FIRST:** Use the "reasoning_scratchpad" to analyze context and timestamps BEFORE outputting facts.
- **NO MIXING:** Be extremely careful to attribute facts to the correct person. 
- **FIRST-PERSON PRONOUNS:** If {my_name} says "I am a doctor", then {my_name} is the doctor. If {sender_name} says "I am a doctor", then {sender_name} is the doctor.
"""

# Dedicated prompt for generating executive summaries from a full profile
EXECUTIVE_SUMMARY_PROMPT = """\
You are writing an executive summary for a personal CRM contact profile. Based on the extracted facts and relationships below, write a concise 2-4 sentence summary that captures who this person is, what they do, and their key characteristics.

## Contact: {display_name}

## Extracted Facts
{facts_block}

## Relationships
{relationships_block}

## Instructions
- Write in third person (e.g., "{display_name} is a...")
- Focus on the most important and high-confidence facts
- Mention their profession, location, and key interests if known
- If facts are marked as "past", acknowledge them as historical context, not current reality
- Be concise but comprehensive — this should give someone a quick understanding of who this person is
- Do NOT include speculative information or low-confidence details
- Write ONLY the summary paragraph, nothing else — no headers, no bullet points
"""

EXECUTIVE_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
    },
    "required": ["summary"],
}

# Prompt for group chat summarization
GROUP_CHAT_SUMMARY_PROMPT = """\
Summarize the following group chat conversation in 2-3 sentences. Focus on the main topics discussed and any plans or decisions made.

## Group Chat: {chat_name}
## Participants: {participants}

## Messages
{messages_block}

Write ONLY the summary paragraph, nothing else.
"""

GROUP_CHAT_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
    },
    "required": ["summary"],
}


class ProfileExtractor:
    def __init__(self):
        self._gemini = GeminiClient()
        self._store = DataStore(config.DATA_DIR / "echo_nosql.json")
        self._profiles: dict[str, ContactProfile] = self._store.get_all_profiles()
        self._group_chats: dict[str, GroupChatSummary] = {}
        self._processed_line_count = self._get_processed_count()
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
            "group_chats": {
                cid: gc.model_dump() for cid, gc in self._group_chats.items()
            },
            "discoveries": discoveries, 
            "last_extraction": datetime.now(timezone.utc).isoformat(),
            "total_contacts": len(self._profiles),
            "processed_lines": processed_lines
        }
        temp_file = config.CONTACTS_FILE.with_suffix(f".tmp.{os.getpid()}")
        lock = FileLock(f"{config.CONTACTS_FILE}.lock")
        try:
            with lock.acquire(timeout=10):
                with open(temp_file, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                temp_file.replace(config.CONTACTS_FILE)
        except Exception as e:
            logger.error(f"Failed to save profiles: {e}")
            if temp_file.exists():
                temp_file.unlink()

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
        batch_size_lines = 5000 
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

        # Post-extraction: generate executive summaries for all profiles
        if total_updated > 0:
            logger.info("--- Generating Executive Summaries ---")
            await self._generate_executive_summaries()
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
        group_chat_tasks = []
        chunk_size = getattr(config, "EXTRACTION_BATCH_SIZE", 50)
        
        for chat_id, messages in messages_by_chat.items():
            meaningful = [m for m in messages if len(m.get("text", "")) > 3]
            if not meaningful: continue
            
            chat_type = meaningful[0].get("chat_type", "single")
            
            other_participants = list(set(
                m.get("sender_name") for m in meaningful 
                if m.get("sender_name") and not m.get("is_self", False)
            ))
            other_name = other_participants[0] if other_participants else "Unknown"
            chat_name = meaningful[0].get("chat_name", other_name)

            if chat_type == "group":
                # Group chats: attribute facts to individual senders, don't create group profile
                group_chat_tasks.append({
                    "chat_id": chat_id,
                    "chat_name": chat_name,
                    "participants": other_participants,
                    "messages": meaningful,
                })
                continue

            for i in range(0, len(meaningful), chunk_size):
                chunk = meaningful[i:i + chunk_size]
                all_tasks_metadata.append({
                    "sender_name": chat_name,
                    "sender_id": chat_id,
                    "chat_type": chat_type,
                    "chunk": chunk
                })

        total_tasks = len(all_tasks_metadata)
        contacts_updated_set = set()
        completed_count = 0

        if total_tasks > 0:
            logger.info(f"  Single Chat Tasks: {total_tasks} chunks")
            
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
                        partner_profile.chat_type = metadata.get("chat_type", "single")

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

        # Process group chats: attribute to individual senders, save group summary
        if group_chat_tasks:
            logger.info(f"  Group Chat Tasks: {len(group_chat_tasks)} chats")
            for gc_meta in group_chat_tasks:
                updated = await self._process_group_chat(gc_meta)
                contacts_updated_set.update(updated)

        return len(contacts_updated_set)

    async def _process_group_chat(self, gc_meta: dict) -> set[str]:
        """Process a group chat: attribute facts to individual senders, save group summary."""
        chat_id = gc_meta["chat_id"]
        chat_name = gc_meta["chat_name"]
        participants = gc_meta["participants"]
        messages = gc_meta["messages"]
        
        contacts_updated = set()
        chunk_size = getattr(config, "EXTRACTION_BATCH_SIZE", 50)

        # Extract facts from group chat messages, grouped by individual sender
        messages_by_sender: dict[str, list[dict]] = {}
        for msg in messages:
            sender = msg.get("sender_name", "Unknown")
            if msg.get("is_self", False):
                sender = config.MY_NAME
            if sender not in messages_by_sender:
                messages_by_sender[sender] = []
            messages_by_sender[sender].append(msg)

        # Process each sender's messages as if they were a 1-on-1 conversation
        for sender_name, sender_msgs in messages_by_sender.items():
            if sender_name == config.MY_NAME:
                continue  # Skip self messages for group extraction
            
            for i in range(0, len(sender_msgs), chunk_size):
                chunk = sender_msgs[i:i + chunk_size]
                async with self._semaphore:
                    result = await self._extract_facts_async(
                        sender_name, chat_id, chunk
                    )
                if result:
                    for fact in result.extractions:
                        subj_name = fact.subject_name
                        if not subj_name: continue
                        
                        target_profile = None
                        if subj_name.lower() in ["self", config.MY_NAME.lower()]:
                            target_profile = self._get_or_create_profile(config.MY_NAME, config.MY_NAME)
                            fact.is_first_party = True
                        elif subj_name.lower() == sender_name.lower():
                            target_profile = self._get_or_create_profile(sender_name, sender_name)
                        else:
                            target_profile = self.get_profile(subj_name)
                            if not target_profile:
                                target_profile = self._get_or_create_profile(subj_name, subj_name)
                        
                        if target_profile:
                            target_profile.add_fact(fact)
                            contacts_updated.add(target_profile.contact_id)

                    for rel in result.relationships:
                        sender_profile = self._get_or_create_profile(sender_name, sender_name)
                        sender_profile.add_relationship(rel)
                        contacts_updated.add(sender_profile.contact_id)

        # Generate a group chat summary
        try:
            gc_summary = await self._summarize_group_chat(chat_id, chat_name, participants, messages)
            self._group_chats[chat_id] = gc_summary
        except Exception as e:
            logger.warning(f"Failed to generate group chat summary for {chat_name}: {e}")

        return contacts_updated

    async def _summarize_group_chat(
        self, chat_id: str, chat_name: str, participants: list[str], messages: list[dict]
    ) -> GroupChatSummary:
        """Generate a summary for a group chat conversation."""
        formatted = []
        for msg in messages[-50:]:  # Last 50 messages for summary
            ts = msg.get("timestamp", "")[:16]
            sender = config.MY_NAME if msg.get("is_self", False) else msg.get("sender_name", "Unknown")
            text = msg.get("text", "")
            formatted.append(f"[{ts}] {sender}: {text}")

        prompt = GROUP_CHAT_SUMMARY_PROMPT.format(
            chat_name=chat_name,
            participants=", ".join(participants),
            messages_block="\n".join(formatted),
        )

        async with self._semaphore:
            try:
                response = await self._gemini.generate_async(
                    prompt,
                    json_schema=GROUP_CHAT_SUMMARY_SCHEMA,
                    temperature=0.2,
                    max_output_tokens=512,
                )
                if response:
                    data = json.loads(response)
                    summary_text = data.get("summary", "")
                else:
                    summary_text = ""
            except Exception as e:
                logger.warning(f"Group chat summary generation failed: {e}")
                summary_text = ""

        return GroupChatSummary(
            chat_id=chat_id,
            display_name=chat_name,
            participant_names=participants,
            summary=summary_text,
        )

    def _get_or_create_profile(self, contact_id: str, display_name: str, chat_type: str = "single") -> ContactProfile:
        # 1. Exact match by ID
        if contact_id in self._profiles:
            return self._profiles[contact_id]
            
        # 2. Try match by display name (Fuzzy/Exact) to merge identities across platforms
        # We only do this for single chats to avoid merging group chats incorrectly
        if chat_type == "single":
            for profile in self._profiles.values():
                if profile.display_name.lower() == display_name.lower():
                    # Link this platform ID to the existing profile
                    logger.info(f"  Merging platform ID '{contact_id}' into existing profile for '{display_name}'")
                    self._profiles[contact_id] = profile
                    return profile

        # 3. Create new profile
        new_profile = ContactProfile(contact_id=contact_id, display_name=display_name, chat_type=chat_type)
        self._profiles[contact_id] = new_profile
        return new_profile

    async def _extract_facts_async(self, sender_name: str, sender_id: str, messages: list[dict[str, Any]]) -> ExtractionResult | None:
        formatted_messages = []
        for msg in messages:
            ts = msg.get("timestamp", "")[:16]
            is_self = msg.get("is_self", False)
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
                response = await self._gemini.generate_async(
                    prompt,
                    json_schema=EXTRACTION_SCHEMA,
                    temperature=0.1,
                    max_output_tokens=2048,
                )
                if not response:
                    continue
                data = json.loads(response)
                return ExtractionResult.model_validate(data)
            except Exception as e:
                logger.debug(f"Extraction attempt {attempt + 1} failed: {e}")
                continue
        return None

    async def _generate_executive_summaries(self):
        """Post-extraction pass: generate comprehensive executive summaries for all profiles."""
        profiles_to_summarize = [
            p for p in self._profiles.values()
            if p.chat_type == "single" and len(p.facts) > 0
            and p.display_name != config.MY_NAME
        ]

        if not profiles_to_summarize:
            return

        logger.info(f"  Generating summaries for {len(profiles_to_summarize)} contacts...")

        async def summarize_one(profile: ContactProfile):
            async with self._semaphore:
                return await self._generate_single_summary(profile)

        tasks = [asyncio.ensure_future(summarize_one(p)) for p in profiles_to_summarize]
        completed = 0

        for future in asyncio.as_completed(tasks):
            profile, summary = await future
            completed += 1
            if summary:
                profile.summary = summary
                logger.debug(f"  Summary generated for {profile.display_name}")
            if completed % 10 == 0 or completed == len(tasks):
                logger.info(f"  Summary Progress: {completed}/{len(tasks)}")

    async def _generate_single_summary(self, profile: ContactProfile) -> tuple[ContactProfile, str]:
        """Generate an executive summary for a single contact profile."""
        # Format facts as a readable block
        facts_lines = []
        for f in profile.facts:
            temporal = f" [{f.temporal_status}]" if f.temporal_status != "unknown" else ""
            source = "self-reported" if f.is_first_party else "third-party"
            facts_lines.append(f"- [{f.category}] {f.value} (confidence: {f.confidence}, source: {source}{temporal})")

        # Format relationships
        rel_lines = []
        for r in profile.relationships:
            rel_lines.append(f"- {r.type}: {r.target_name} — {r.context or 'no context'} (confidence: {r.confidence})")

        prompt = EXECUTIVE_SUMMARY_PROMPT.format(
            display_name=profile.display_name,
            facts_block="\n".join(facts_lines) if facts_lines else "No facts extracted.",
            relationships_block="\n".join(rel_lines) if rel_lines else "No relationships extracted.",
        )

        try:
            response = await self._gemini.generate_async(
                prompt,
                json_schema=EXECUTIVE_SUMMARY_SCHEMA,
                temperature=0.3,
                max_output_tokens=512,
            )
            if response:
                data = json.loads(response)
                return profile, data.get("summary", "")
        except Exception as e:
            logger.warning(f"Summary generation failed for {profile.display_name}: {e}")

        return profile, ""

    def get_all_profiles(self) -> dict[str, ContactProfile]:
        return self._profiles

    def get_profile(self, contact_name: str) -> ContactProfile | None:
        query = contact_name.lower()
        for profile in self._profiles.values():
            if query in profile.display_name.lower():
                return profile
        return None
