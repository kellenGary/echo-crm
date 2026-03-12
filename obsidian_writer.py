"""
Obsidian Writer — generates interlinked Obsidian notes from contact profiles
and message history.

Responsibilities:
  - Read extracted contact profiles and raw message logs
  - Use the LLM to extract entities (people, places, topics) and relationships
  - Generate Obsidian markdown notes with [[wiki-links]] and YAML frontmatter
  - Organize notes into People/, Places/, and Topics/ subdirectories

The resulting graph in Obsidian lets you visually explore connections
between people, locations, interests, and conversations.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

import config
from profile_extractor import ProfileExtractor

logger = logging.getLogger(__name__)

# Prompt for extracting entities and relationships from a contact's messages
ENTITY_EXTRACTION_PROMPT = """\
You are a knowledge graph extraction assistant. Given chat messages involving \
a contact, extract ALL entities and relationships mentioned.

Extract:
1. **People** — names, nicknames, or references to specific individuals
2. **Places** — cities, states, countries, venues, restaurants, neighborhoods
3. **Topics** — interests, hobbies, recurring themes, work-related topics
4. **Events** — planned events, trips, gatherings, important dates
5. **Relationships** — how entities connect (e.g., "works at", "lives in", "friends with")

Respond ONLY with valid JSON:
{{
  "people": [
    {{"name": "...", "context": "brief context from messages"}}
  ],
  "places": [
    {{"name": "...", "context": "brief context"}}
  ],
  "topics": [
    {{"name": "...", "context": "brief context"}}
  ],
  "events": [
    {{"name": "...", "date": "if known", "context": "brief context"}}
  ],
  "relationships": [
    {{"from": "entity1", "to": "entity2", "type": "relationship type", "context": "brief context"}}
  ]
}}

If nothing is found for a category, use an empty array.

---
Contact: **{contact_name}**
Messages:

{messages}
"""


def _sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename."""
    # Remove or replace characters that are invalid in filenames
    sanitized = re.sub(r'[<>:"/\\|?*]', '', name)
    sanitized = sanitized.strip('. ')
    return sanitized or "Unknown"


class ObsidianWriter:
    """
    Generates interlinked Obsidian markdown notes from Beeper data.

    Directory structure:
        Beeper Intelligence/
        ├── People/          ← One note per contact
        ├── Places/          ← One note per location
        ├── Topics/          ← One note per interest/theme
        └── _Index.md        ← Overview with links to everything
    """

    def __init__(self):
        self._base_dir = config.OBSIDIAN_BEEPER_DIR
        self._people_dir = self._base_dir / "People"
        self._places_dir = self._base_dir / "Places"
        self._topics_dir = self._base_dir / "Topics"
        self._ollama_url = config.OLLAMA_BASE_URL
        self._model = config.OLLAMA_MODEL
        self._extractor = ProfileExtractor()

        # Create directories
        for d in [self._base_dir, self._people_dir, self._places_dir, self._topics_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def generate_all(self) -> dict[str, int]:
        """
        Generate all Obsidian notes from the current data.
        Returns counts of notes created per category.
        """
        profiles = self._extractor.get_all_profiles()
        if not profiles:
            logger.warning("No contact profiles found. Run sync + extract first.")
            return {"people": 0, "places": 0, "topics": 0}

        # Load raw messages grouped by contact for entity extraction
        messages_by_contact = self._load_messages_by_contact()

        all_places: dict[str, dict[str, Any]] = {}
        all_topics: dict[str, dict[str, Any]] = {}
        people_notes: list[dict[str, Any]] = []

        for contact_id, profile in profiles.items():
            contact_name = profile.display_name
            logger.info(f"Processing {contact_name}...")

            # Get this contact's messages
            contact_msgs = messages_by_contact.get(contact_id, [])

            # Extract entities via LLM
            entities = self._extract_entities(contact_name, contact_msgs)

            # Build people note data
            person_data = {
                "name": contact_name,
                "contact_id": contact_id,
                "profile": profile,
                "entities": entities,
                "messages": contact_msgs,
            }
            people_notes.append(person_data)

            # Accumulate places and topics across all contacts
            for place in entities.get("places", []):
                place_name = place.get("name", "").strip()
                if not place_name:
                    continue
                key = place_name.lower()
                if key not in all_places:
                    all_places[key] = {
                        "name": place_name,
                        "mentioned_by": [],
                        "contexts": [],
                    }
                all_places[key]["mentioned_by"].append(contact_name)
                if place.get("context"):
                    all_places[key]["contexts"].append(
                        f"{contact_name}: {place['context']}"
                    )

            for topic in entities.get("topics", []):
                topic_name = topic.get("name", "").strip()
                if not topic_name:
                    continue
                key = topic_name.lower()
                if key not in all_topics:
                    all_topics[key] = {
                        "name": topic_name,
                        "mentioned_by": [],
                        "contexts": [],
                    }
                all_topics[key]["mentioned_by"].append(contact_name)
                if topic.get("context"):
                    all_topics[key]["contexts"].append(
                        f"{contact_name}: {topic['context']}"
                    )

        # Write all notes
        people_count = 0
        for person in people_notes:
            self._write_person_note(person, all_places, all_topics)
            people_count += 1

        places_count = 0
        for place_data in all_places.values():
            self._write_place_note(place_data)
            places_count += 1

        topics_count = 0
        for topic_data in all_topics.values():
            self._write_topic_note(topic_data)
            topics_count += 1

        # Write index
        self._write_index(people_notes, all_places, all_topics)

        counts = {"people": people_count, "places": places_count, "topics": topics_count}
        logger.info(
            f"Obsidian notes generated: {people_count} people, "
            f"{places_count} places, {topics_count} topics"
        )
        return counts

    # ------------------------------------------------------------------
    # Note writers
    # ------------------------------------------------------------------

    def _write_person_note(
        self,
        person: dict[str, Any],
        all_places: dict[str, dict],
        all_topics: dict[str, dict],
    ):
        """Write an Obsidian note for a person."""
        profile = person["profile"]
        entities = person["entities"]
        name = person["name"]
        safe_name = _sanitize_filename(name)

        # Build wiki-links for related entities
        place_links = []
        for p in entities.get("places", []):
            pname = p.get("name", "").strip()
            if pname:
                place_links.append(f"[[{_sanitize_filename(pname)}]]")

        topic_links = []
        for t in entities.get("topics", []):
            tname = t.get("name", "").strip()
            if tname:
                topic_links.append(f"[[{_sanitize_filename(tname)}]]")

        people_links = []
        for p in entities.get("people", []):
            pname = p.get("name", "").strip()
            if pname and pname != name:
                people_links.append(f"[[{_sanitize_filename(pname)}]]")

        # YAML frontmatter
        lines = [
            "---",
            f"type: person",
            f"name: \"{name}\"",
            f"contact_id: \"{person['contact_id']}\"",
            f"messages_analyzed: {profile.message_count}",
            f"last_updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            f"tags: [beeper, contact]",
            "---",
            "",
            f"# {name}",
            "",
        ]

        # Facts section
        if profile.facts:
            lines.append("## Known Facts")
            lines.append("")
            for fact in profile.facts:
                category = fact.get("category", "Other")
                value = fact.get("value", "")
                confidence = fact.get("confidence", "")
                source = fact.get("source_quote", "")

                line = f"- **{category}**: {value}"
                if confidence:
                    line += f" `({confidence})`"
                lines.append(line)
                if source:
                    lines.append(f"  - > \"{source}\"")
            lines.append("")

        # Relationships section
        relationships = entities.get("relationships", [])
        if relationships:
            lines.append("## Relationships")
            lines.append("")
            for rel in relationships:
                from_e = rel.get("from", "")
                to_e = rel.get("to", "")
                rel_type = rel.get("type", "related to")
                context = rel.get("context", "")

                to_safe = _sanitize_filename(to_e)
                from_safe = _sanitize_filename(from_e)

                if from_e.lower() == name.lower():
                    lines.append(f"- **{rel_type}** → [[{to_safe}]]")
                elif to_e.lower() == name.lower():
                    lines.append(f"- [[{from_safe}]] **{rel_type}** → this person")
                else:
                    lines.append(f"- [[{from_safe}]] **{rel_type}** [[{to_safe}]]")

                if context:
                    lines.append(f"  - {context}")
            lines.append("")

        # Events
        events = entities.get("events", [])
        if events:
            lines.append("## Events")
            lines.append("")
            for event in events:
                event_name = event.get("name", "")
                date = event.get("date", "")
                context = event.get("context", "")
                line = f"- **{event_name}**"
                if date:
                    line += f" ({date})"
                lines.append(line)
                if context:
                    lines.append(f"  - {context}")
            lines.append("")

        # Connected entities
        if people_links:
            lines.append("## Connected People")
            lines.append("")
            for link in people_links:
                lines.append(f"- {link}")
            lines.append("")

        if place_links:
            lines.append("## Places")
            lines.append("")
            for link in place_links:
                lines.append(f"- {link}")
            lines.append("")

        if topic_links:
            lines.append("## Interests & Topics")
            lines.append("")
            for link in topic_links:
                lines.append(f"- {link}")
            lines.append("")

        # Recent messages snippet
        messages = person.get("messages", [])
        if messages:
            lines.append("## Recent Messages")
            lines.append("")
            for msg in messages[-10:]:
                ts = msg.get("timestamp", "")[:10]
                text = msg.get("text", "")
                sender = msg.get("sender_name", "?")
                is_self = msg.get("is_self", False)
                who = "You" if is_self else sender
                lines.append(f"> **{who}** ({ts}): {text}")
                lines.append("")

        filepath = self._people_dir / f"{safe_name}.md"
        filepath.write_text("\n".join(lines), encoding="utf-8")

    def _write_place_note(self, place_data: dict[str, Any]):
        """Write an Obsidian note for a place."""
        name = place_data["name"]
        safe_name = _sanitize_filename(name)
        mentioned_by = list(set(place_data["mentioned_by"]))
        contexts = place_data["contexts"]

        lines = [
            "---",
            f"type: place",
            f"name: \"{name}\"",
            f"mentioned_by_count: {len(mentioned_by)}",
            f"last_updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            f"tags: [beeper, place]",
            "---",
            "",
            f"# {name}",
            "",
            "## Mentioned By",
            "",
        ]

        for person in mentioned_by:
            safe_person = _sanitize_filename(person)
            lines.append(f"- [[{safe_person}]]")

        lines.append("")

        if contexts:
            lines.append("## Context")
            lines.append("")
            for ctx in contexts:
                lines.append(f"- {ctx}")
            lines.append("")

        filepath = self._places_dir / f"{safe_name}.md"
        filepath.write_text("\n".join(lines), encoding="utf-8")

    def _write_topic_note(self, topic_data: dict[str, Any]):
        """Write an Obsidian note for a topic/interest."""
        name = topic_data["name"]
        safe_name = _sanitize_filename(name)
        mentioned_by = list(set(topic_data["mentioned_by"]))
        contexts = topic_data["contexts"]

        lines = [
            "---",
            f"type: topic",
            f"name: \"{name}\"",
            f"mentioned_by_count: {len(mentioned_by)}",
            f"last_updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            f"tags: [beeper, topic]",
            "---",
            "",
            f"# {name}",
            "",
            "## Discussed By",
            "",
        ]

        for person in mentioned_by:
            safe_person = _sanitize_filename(person)
            lines.append(f"- [[{safe_person}]]")

        lines.append("")

        if contexts:
            lines.append("## Context")
            lines.append("")
            for ctx in contexts:
                lines.append(f"- {ctx}")
            lines.append("")

        filepath = self._topics_dir / f"{safe_name}.md"
        filepath.write_text("\n".join(lines), encoding="utf-8")

    def _write_index(
        self,
        people: list[dict],
        places: dict[str, dict],
        topics: dict[str, dict],
    ):
        """Write the master index note."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        lines = [
            "---",
            "type: index",
            f"last_updated: {now}",
            "tags: [beeper, index]",
            "---",
            "",
            "# 🤖 Beeper Intelligence Network",
            "",
            f"*Last synced: {now}*",
            "",
            f"**{len(people)}** people · **{len(places)}** places · **{len(topics)}** topics",
            "",
            "---",
            "",
            "## 👤 People",
            "",
        ]

        for person in sorted(people, key=lambda p: p["name"]):
            safe_name = _sanitize_filename(person["name"])
            fact_count = len(person["profile"].facts)
            lines.append(f"- [[{safe_name}]] — {fact_count} facts")

        lines.extend(["", "## 📍 Places", ""])
        for place in sorted(places.values(), key=lambda p: p["name"]):
            safe_name = _sanitize_filename(place["name"])
            count = len(set(place["mentioned_by"]))
            lines.append(f"- [[{safe_name}]] — mentioned by {count} contact(s)")

        lines.extend(["", "## 💡 Topics", ""])
        for topic in sorted(topics.values(), key=lambda t: t["name"]):
            safe_name = _sanitize_filename(topic["name"])
            count = len(set(topic["mentioned_by"]))
            lines.append(f"- [[{safe_name}]] — discussed by {count} contact(s)")

        lines.append("")

        filepath = self._base_dir / "_Index.md"
        filepath.write_text("\n".join(lines), encoding="utf-8")

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_messages_by_contact(self) -> dict[str, list[dict[str, Any]]]:
        """Load raw messages grouped by sender_id."""
        messages: dict[str, list[dict[str, Any]]] = {}
        if not config.RAW_LOG_FILE.exists():
            return messages

        with open(config.RAW_LOG_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Group by sender_name to merge text messages and Beeper messages
                sender_name = record.get("sender_name", record.get("sender_id", ""))
                if sender_name not in messages:
                    messages[sender_name] = []
                messages[sender_name].append(record)

        return messages

    # ------------------------------------------------------------------
    # LLM entity extraction
    # ------------------------------------------------------------------

    def _extract_entities(
        self, contact_name: str, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Extract entities and relationships from a contact's messages."""
        if not messages:
            return {"people": [], "places": [], "topics": [], "events": [], "relationships": []}

        # Format messages for the prompt  
        formatted = []
        for msg in messages[-50:]:
            ts = msg.get("timestamp", "")[:10]
            text = msg.get("text", "")
            is_self = msg.get("is_self", False)
            sender = "You" if is_self else msg.get("sender_name", "?")
            chat = msg.get("chat_name", "")
            formatted.append(f"[{ts}] ({chat}) {sender}: {text}")

        base_prompt = ENTITY_EXTRACTION_PROMPT.format(
            contact_name=contact_name,
            messages="\n".join(formatted),
        )

        prompt = base_prompt
        max_retries = 2
        
        for attempt in range(max_retries):
            response = self._call_ollama(prompt)
            if not response:
                break

            try:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                if json_start == -1 or json_end == 0:
                    raise ValueError("No JSON object found in response")
                result = json.loads(response[json_start:json_end])
                return result
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse entity extraction for {contact_name} on attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    prompt = base_prompt + f"\n\nERROR: The previous response was invalid JSON: {str(e)}. Please try again and return ONLY valid JSON. Make sure to properly escape quotes within strings (using \\\"), remove any trailing commas, and preserve the original message quotes perfectly."
                else:
                    logger.error(f"Giving up on {contact_name} after {max_retries} attempts.")

        return {"people": [], "places": [], "topics": [], "events": [], "relationships": []}

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
                            "temperature": 0.1,
                            "num_predict": 2048,
                        },
                    },
                )
                resp.raise_for_status()
                return resp.json().get("response", "")
        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            return ""
