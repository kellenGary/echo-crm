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

            # We build a temporary entities dict for Obsidian's structure
            entities = {"places": [], "topics": [], "people": []}
            
            for fact in profile.facts:
                if fact.category == "Location":
                    entities["places"].append({"name": fact.value, "context": fact.source_quote})
                elif fact.category == "Interest":
                    entities["topics"].append({"name": fact.value, "context": fact.source_quote})
                elif fact.category == "Family":
                    entities["people"].append({"name": fact.value, "context": fact.source_quote})

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
            for place in entities["places"]:
                place_name = place["name"].strip()
                if not place_name: continue
                key = place_name.lower()
                if key not in all_places:
                    all_places[key] = {"name": place_name, "mentioned_by": [], "contexts": []}
                all_places[key]["mentioned_by"].append(contact_name)
                if place.get("context"):
                    all_places[key]["contexts"].append(f"{contact_name}: {place['context']}")

            for topic in entities["topics"]:
                topic_name = topic["name"].strip()
                if not topic_name: continue
                key = topic_name.lower()
                if key not in all_topics:
                    all_topics[key] = {"name": topic_name, "mentioned_by": [], "contexts": []}
                all_topics[key]["mentioned_by"].append(contact_name)
                if topic.get("context"):
                    all_topics[key]["contexts"].append(f"{contact_name}: {topic['context']}")

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
        """Write a beautiful Obsidian note for a person based on Format File.md."""
        profile = person["profile"]
        name = person["name"]
        safe_name = _sanitize_filename(name)

        # Organize facts by template sections
        sections = {
            "identity": [],
            "biographical": [],
            "professional": [],
            "interest": [],
            "social": []
        }
        
        # Frontmatter variables
        fm = {
            "aliases": [],
            "tags": ["contact", "beeper"],
            "relationship": "Contact",
            "location": "Unknown",
            "company": "Unknown",
            "role": "Unknown",
            "birthday": "Unknown"
        }

        for fact in profile.facts:
            cat = fact.category.lower()
            val = fact.value
            
            # Map categories to sections
            if "identity" in cat: sections["identity"].append(fact)
            elif "biographical" in cat or "location" in cat or "education" in cat: sections["biographical"].append(fact)
            elif "professional" in cat or "work" in cat: sections["professional"].append(fact)
            elif "interest" in cat or "hobby" in cat: sections["interest"].append(fact)
            elif "social" in cat or "family" in cat or "relationship" in cat: sections["social"].append(fact)
            else: sections["interest"].append(fact) # Fallback

            # Fill frontmatter if possible
            if "location" in cat: fm["location"] = val
            if "work" in cat or "company" in cat: fm["company"] = val
            if "role" in cat: fm["role"] = val
            if "birthday" in cat: fm["birthday"] = val
            if "identity" in cat and "name" in cat: fm["aliases"].append(val)
            if "social" in cat and "relation" in cat: fm["relationship"] = val

        # YAML frontmatter
        lines = [
            "---",
            f"aliases: {json.dumps(fm['aliases'])}",
            f"tags: {json.dumps(fm['tags'])}",
            f"relationship: \"{fm['relationship']}\"",
            f"location: \"{fm['location']}\"",
            f"company: \"{fm['company']}\"",
            f"role: \"{fm['role']}\"",
            f"birthday: \"{fm['birthday']}\"",
            f"last_updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            "---",
            "",
            f"# {name}",
            "",
            f"> **Quick Summary:**",
            f"> {profile.summary if profile.summary else 'No summary available yet.'}",
            "",
            "## 🪪 Identity & Bio",
        ]

        def add_section_facts(fact_list):
            if not fact_list:
                lines.append("* No details recorded yet.")
            for f in fact_list:
                line = f"* **{f.category}:** {f.value}"
                if not f.is_first_party:
                    line += " ℹ️"
                lines.append(line)

        add_section_facts(sections["identity"] + sections["biographical"])

        lines.append("\n## 💼 Professional")
        add_section_facts(sections["professional"])

        lines.append("\n## 🎯 Interests & Hobbies")
        add_section_facts(sections["interest"])

        lines.append("\n## 🤝 Social Context")
        add_section_facts(sections["social"])

        lines.append("\n---")
        lines.append("## 📝 Extraction Log")
        lines.append("*Keep a running log of the raw facts extracts.*")
        lines.append("")

        # Sorted log
        sorted_facts = sorted(profile.facts, key=lambda x: x.extracted_at, reverse=True)
        for f in sorted_facts:
            date_str = f.extracted_at[:10]
            party_str = "First-party" if f.is_first_party else "Third-party"
            lines.append(f"- **[{date_str}]** `{f.category}` - \"{f.source_quote}\" → **{f.value}** (Confidence: {f.confidence.capitalize()}) | *{party_str}*")

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
        """Load raw messages grouped by sender_id or sender_name."""
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
                    # Use sender_id if available, fallback to name
                    # For self messages, ensure they go to config.MY_NAME's bucket
                    if record.get("is_self"):
                        sender_key = config.MY_NAME
                    else:
                        sender_key = record.get("sender_id", record.get("sender_name", "unknown"))
                    
                    if sender_key not in messages:
                        messages[sender_key] = []
                    messages[sender_key].append(record)
                except json.JSONDecodeError:
                    continue

        return messages

    # Removed _extract_entities to consolidate extraction into ProfileExtractor.
