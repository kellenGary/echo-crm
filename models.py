from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator

class Fact(BaseModel):
    subject_name: str = Field("Self", description="The name of the person this fact is about (use 'Self' for the sender)")
    category: str = Field(..., description="Work|Location|Family|Interest|Preference|Other")
    value: str = Field(..., description="The specific fact content")
    confidence: str = Field("medium", description="high|medium|low")
    source_quote: Optional[str] = Field(None, description="Exact snippet from the text")
    is_first_party: bool = Field(True, description="True if the subject is speaking about themselves")
    temporal_status: str = Field("unknown", description="current|past|unknown — whether this fact is still true")
    extracted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: str) -> str:
        if v.lower() not in ["high", "medium", "low"]:
            return "medium"
        return v.lower()

    @field_validator("temporal_status")
    @classmethod
    def validate_temporal_status(cls, v: str) -> str:
        if v.lower() not in ["current", "past", "unknown"]:
            return "unknown"
        return v.lower()

class Relationship(BaseModel):
    target_name: str
    target_id: Optional[str] = None
    type: str = Field(..., description="friend|colleague|family|knows|works_at|lives_in")
    context: Optional[str] = None
    confidence: str = "medium"
    extracted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("type")
    @classmethod
    def normalize_type(cls, v: str) -> str:
        """Normalize compound types like 'friend|colleague' → first value, lowercased."""
        return v.split("|")[0].strip().lower()

class ExtractionResult(BaseModel):
    reasoning_scratchpad: Optional[str] = None
    extractions: list[Fact] = []
    relationships: list[Relationship] = []
    summary_of_sender: Optional[str] = None

class ContactProfile(BaseModel):
    contact_id: str
    display_name: str
    facts: list[Fact] = []
    relationships: list[Relationship] = []
    summary: str = ""
    chat_type: str = "single"
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    message_count: int = 0

    def add_fact(self, new_fact: Fact):
        """
        Merge a single fact into the profile with attribute-level priority.
        PRIORITY RULE: First-party data (Self) cannot be overwritten by third-party data.
        """
        if not new_fact.value:
            return

        existing_idx = -1
        for i, f in enumerate(self.facts):
            if f.category == new_fact.category and f.value.lower() == new_fact.value.lower():
                existing_idx = i
                break
            
            if new_fact.category in ["Work", "Location", "Biographical"] and f.category == new_fact.category:
                if not f.is_first_party and new_fact.is_first_party:
                    existing_idx = i
                    break

        if existing_idx >= 0:
            existing_fact = self.facts[existing_idx]
            if (new_fact.is_first_party and not existing_fact.is_first_party) or \
               (new_fact.is_first_party == existing_fact.is_first_party and 
                new_fact.confidence == "high" and existing_fact.confidence != "high"):
                self.facts[existing_idx] = new_fact
        else:
            self.facts.append(new_fact)

        self.last_updated = datetime.now(timezone.utc).isoformat()

    def add_relationship(self, rel: Relationship):
        """Add or update a relationship. Rejects low confidence and deduplicates."""
        # Skip low-confidence relationships
        if rel.confidence.lower() == "low":
            return

        rel_target = rel.target_name.lower().strip()
        rel_type = rel.type.lower().strip()

        for existing in self.relationships:
            existing_target = existing.target_name.lower().strip()
            existing_type = existing.type.lower().strip()

            # Same target — check for type overlap
            if existing_target == rel_target:
                # Exact type match → skip
                if existing_type == rel_type:
                    return
                # If one is 'knows' and the other is more specific, keep the specific one
                if rel_type == "knows":
                    return  # already have a more specific type

        self.relationships.append(rel)
        self.last_updated = datetime.now(timezone.utc).isoformat()

class GroupChatSummary(BaseModel):
    chat_id: str
    display_name: str
    participant_names: list[str] = []
    summary: str = ""
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class IntelligenceGraph(BaseModel):
    nodes: list[dict[str, Any]] = [] # {id, label, type, val}
    links: list[dict[str, Any]] = [] # {source, target, label}
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
