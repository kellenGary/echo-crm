"""
Echo CRM — SQLAlchemy 2.0 ORM models.

Maps to the schema defined in ``init_schema.sql``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


# ── 1. Contact ──────────────────────────────────────────────────────────────

class Contact(Base):
    """Lean, core identity of a person."""

    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.uuid_generate_v4()
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unstructured_profile: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(default=func.now(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), server_default=func.now(), onupdate=func.now())

    # ── Relationships ────────────────────────────────────────────────────
    linked_accounts: Mapped[List[LinkedAccount]] = relationship(
        back_populates="contact", cascade="all, delete-orphan", lazy="selectin"
    )
    contact_facts: Mapped[List[ContactFact]] = relationship(
        back_populates="contact", cascade="all, delete-orphan", lazy="selectin"
    )

    # Self-referencing many-to-many via the relationships table
    relationships_as_1: Mapped[List[Relationship]] = relationship(
        foreign_keys="[Relationship.contact_id_1]", back_populates="contact_1", cascade="all, delete-orphan"
    )
    relationships_as_2: Mapped[List[Relationship]] = relationship(
        foreign_keys="[Relationship.contact_id_2]", back_populates="contact_2", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Contact {self.display_name!r} ({self.id})>"


# ── 2. Linked Account ──────────────────────────────────────────────────────

class LinkedAccount(Base):
    """Ties a third-party platform identity to a core contact."""

    __tablename__ = "linked_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="uq_linked_accounts_provider_id"),
        Index("idx_linked_accounts_contact_id", "contact_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.uuid_generate_v4()
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    username_handle: Mapped[Optional[str]] = mapped_column(String(255))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default="{}")

    # ── Relationships ────────────────────────────────────────────────────
    contact: Mapped[Contact] = relationship(back_populates="linked_accounts")

    def __repr__(self) -> str:
        return f"<LinkedAccount {self.provider}:{self.username_handle or self.provider_id}>"


# ── 3. Relationship (Social Graph Edge) ────────────────────────────────────

class Relationship(Base):
    """Directed edge in the social graph between two contacts."""

    __tablename__ = "relationships"
    __table_args__ = (
        UniqueConstraint("contact_id_1", "contact_id_2", "relationship_type", name="uq_relationships_pair_type"),
        CheckConstraint("contact_id_1 <> contact_id_2", name="chk_no_self_relationship"),
        CheckConstraint("confidence_score BETWEEN 0.0 AND 1.0", name="chk_confidence_range"),
        Index("idx_relationships_contact_1", "contact_id_1"),
        Index("idx_relationships_contact_2", "contact_id_2"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.uuid_generate_v4()
    )
    contact_id_1: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    contact_id_2: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_score: Mapped[Optional[float]] = mapped_column()

    # ── Relationships ────────────────────────────────────────────────────
    contact_1: Mapped[Contact] = relationship(
        foreign_keys=[contact_id_1], back_populates="relationships_as_1"
    )
    contact_2: Mapped[Contact] = relationship(
        foreign_keys=[contact_id_2], back_populates="relationships_as_2"
    )

    def __repr__(self) -> str:
        return f"<Relationship {self.contact_id_1} --[{self.relationship_type}]--> {self.contact_id_2}>"


# ── 4. Message ──────────────────────────────────────────────────────────────

class Message(Base):
    """Raw ingestion queue entry from any messaging platform."""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("provider", "provider_message_id", name="uq_messages_provider_msg"),
        Index("idx_messages_provider_sender", "provider", "sender_provider_id"),
        Index("idx_messages_is_extracted", "is_extracted", postgresql_where="is_extracted = FALSE"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.uuid_generate_v4()
    )
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(512))
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    sender_provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    timestamp: Mapped[Optional[datetime]] = mapped_column()
    is_extracted: Mapped[bool] = mapped_column(default=False, server_default="false")

    def __repr__(self) -> str:
        return f"<Message {self.provider}:{self.provider_message_id} extracted={self.is_extracted}>"


# ── 5. Extracted Fact (RAG Knowledge Base) ──────────────────────────────────

class ExtractedFact(Base):
    """An LLM-generated summary with a vector embedding for semantic search."""

    __tablename__ = "extracted_facts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.uuid_generate_v4()
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # embedding = mapped_column(Vector(768))  # pgvector column — commented out if not available
    source_message_ids: Mapped[list] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(default=func.now(), server_default=func.now())

    # ── Relationships ────────────────────────────────────────────────────
    contact_facts: Mapped[List[ContactFact]] = relationship(
        back_populates="fact", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<ExtractedFact {self.id} summary={self.summary[:40]!r}...>"


# ── 6. Contact–Fact Join ────────────────────────────────────────────────────

class ContactFact(Base):
    """Many-to-many join connecting contacts to shared facts/memories."""

    __tablename__ = "contact_facts"
    __table_args__ = (
        Index("idx_contact_facts_fact_id", "fact_id"),
    )

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True
    )
    fact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extracted_facts.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[Optional[str]] = mapped_column(String(128))

    # ── Relationships ────────────────────────────────────────────────────
    contact: Mapped[Contact] = relationship(back_populates="contact_facts")
    fact: Mapped[ExtractedFact] = relationship(back_populates="contact_facts")

    def __repr__(self) -> str:
        return f"<ContactFact contact={self.contact_id} fact={self.fact_id} role={self.role!r}>"
