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
    extracted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: str) -> str:
        if v.lower() not in ["high", "medium", "low"]:
            return "medium"
        return v.lower()

class Relationship(BaseModel):
    target_name: str
    target_id: Optional[str] = None
    type: str = Field(..., description="friend|colleague|family|knows|works_at|lives_in|parent|child|brother|sister")
    context: Optional[str] = None
    confidence: str = "medium"
    extracted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

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
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    message_count: int = 0

    def add_fact(self, new_fact: Fact):
        """
        Merge a single fact into the profile with attribute-level priority.
        PRIORITY RULE: First-party data (Self) cannot be overwritten by third-party data.
        """
        if not new_fact.value:
            return

        # Deduplication and priority logic
        existing_idx = -1
        for i, f in enumerate(self.facts):
            # Same category and same value (case-insensitive)
            if f.category == new_fact.category and f.value.lower() == new_fact.value.lower():
                existing_idx = i
                break
            
            # Semantic overwrite: If we have a new 'Work' or 'Location' from the person themselves,
            # we should replace the old one even if the value is different.
            if new_fact.category in ["Work", "Location", "Biographical"] and f.category == new_fact.category:
                if (not f.is_first_party and new_fact.is_first_party) or \
                   (f.is_first_party == new_fact.is_first_party and new_fact.confidence == "high"):
                    existing_idx = i
                    break

        if existing_idx >= 0:
            existing_fact = self.facts[existing_idx]
            # Replace if:
            # 1. New fact is first-party and old one isn't
            # 2. Both have same party-status but new confidence is higher
            if (new_fact.is_first_party and not existing_fact.is_first_party) or \
               (new_fact.is_first_party == existing_fact.is_first_party and 
                new_fact.confidence == "high" and existing_fact.confidence != "high"):
                self.facts[existing_idx] = new_fact
        else:
            self.facts.append(new_fact)

        self.last_updated = datetime.now(timezone.utc).isoformat()

    def add_relationship(self, rel: Relationship):
        """Update or add a relationship."""
        existing_idx = -1
        for i, r in enumerate(self.relationships):
            if r.target_name.lower() == rel.target_name.lower() and r.type == rel.type:
                existing_idx = i
                break
        
        if existing_idx >= 0:
            self.relationships[existing_idx] = rel
        else:
            self.relationships.append(rel)
        self.last_updated = datetime.now(timezone.utc).isoformat()

