"""
Echo CRM — Contact Repository.

Database-backed storage layer that replaces the old JSON/TinyDB persistence.
All contact read/write operations go through this class.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db import get_session
from db.models import Contact, LinkedAccount, ExtractedFact, ContactFact

logger = logging.getLogger(__name__)


class ContactRepository:
    """Encapsulates all database operations for contacts and their profiles."""

    # ── Read Operations ─────────────────────────────────────────────────

    def get_all_contacts(self) -> List[Dict[str, Any]]:
        """Return all contacts as dicts (profile stored in unstructured_profile)."""
        session = get_session()
        try:
            contacts = session.query(Contact).all()
            results = []
            for c in contacts:
                profile = dict(c.unstructured_profile) if c.unstructured_profile else {}
                # Ensure core fields are present from the DB row itself
                profile["db_id"] = str(c.id)
                profile.setdefault("display_name", c.display_name)
                profile.setdefault("contact_id", self._get_provider_id(session, c.id) or str(c.id))
                results.append(profile)
            return results
        finally:
            session.close()

    def get_contact(self, contact_db_id: str) -> Optional[Dict[str, Any]]:
        """Return a single contact by its DB UUID."""
        session = get_session()
        try:
            contact = session.query(Contact).filter(Contact.id == contact_db_id).first()
            if not contact:
                return None
            profile = dict(contact.unstructured_profile) if contact.unstructured_profile else {}
            profile["db_id"] = str(contact.id)
            profile.setdefault("display_name", contact.display_name)
            profile.setdefault("contact_id", self._get_provider_id(session, contact.id) or str(contact.id))
            return profile
        finally:
            session.close()

    def get_contact_by_provider_id(self, provider: str, provider_id: str) -> Optional[Dict[str, Any]]:
        """Look up a contact by their platform-specific ID (e.g. imsg thread ID)."""
        session = get_session()
        try:
            linked = (
                session.query(LinkedAccount)
                .filter(LinkedAccount.provider == provider, LinkedAccount.provider_id == provider_id)
                .first()
            )
            if not linked:
                return None
            contact = session.query(Contact).filter(Contact.id == linked.contact_id).first()
            if not contact:
                return None
            profile = dict(contact.unstructured_profile) if contact.unstructured_profile else {}
            profile["db_id"] = str(contact.id)
            profile.setdefault("display_name", contact.display_name)
            profile.setdefault("contact_id", provider_id)
            return profile
        finally:
            session.close()

    def get_contact_by_legacy_id(self, legacy_contact_id: str) -> Optional[Dict[str, Any]]:
        """Look up a contact by the legacy contact_id stored in unstructured_profile."""
        session = get_session()
        try:
            # First try linked_accounts (provider_id match)
            linked = (
                session.query(LinkedAccount)
                .filter(LinkedAccount.provider_id == legacy_contact_id)
                .first()
            )
            if linked:
                contact = session.query(Contact).filter(Contact.id == linked.contact_id).first()
                if contact:
                    profile = dict(contact.unstructured_profile) if contact.unstructured_profile else {}
                    profile["db_id"] = str(contact.id)
                    profile.setdefault("display_name", contact.display_name)
                    profile.setdefault("contact_id", legacy_contact_id)
                    return profile

            # Fallback: scan unstructured_profile for contact_id match
            contacts = session.query(Contact).filter(
                Contact.unstructured_profile["contact_id"].astext == legacy_contact_id
            ).all()
            if contacts:
                c = contacts[0]
                profile = dict(c.unstructured_profile) if c.unstructured_profile else {}
                profile["db_id"] = str(c.id)
                profile.setdefault("display_name", c.display_name)
                profile.setdefault("contact_id", legacy_contact_id)
                return profile
            return None
        finally:
            session.close()

    def get_me(self, my_name: str) -> Optional[Dict[str, Any]]:
        """Return the user's own profile by display name."""
        session = get_session()
        try:
            contact = session.query(Contact).filter(Contact.display_name == my_name).first()
            if not contact:
                return None
            profile = dict(contact.unstructured_profile) if contact.unstructured_profile else {}
            profile["db_id"] = str(contact.id)
            profile.setdefault("display_name", contact.display_name)
            profile.setdefault("contact_id", my_name)
            return profile
        finally:
            session.close()

    # ── Write Operations ────────────────────────────────────────────────

    def upsert_contact(
        self,
        legacy_contact_id: str,
        display_name: str,
        profile_data: Dict[str, Any],
        provider: str = "imsg",
    ) -> str:
        """
        Insert or update a contact. Returns the DB UUID as string.

        - Creates or updates the ``contacts`` row with ``unstructured_profile``.
        - Creates a ``linked_accounts`` row so the legacy ID can be found later.
        """
        session = get_session()
        try:
            # 1. Check if a linked_account already exists for this legacy ID
            linked = (
                session.query(LinkedAccount)
                .filter(LinkedAccount.provider_id == legacy_contact_id)
                .first()
            )

            if linked:
                # Update existing contact
                contact = session.query(Contact).filter(Contact.id == linked.contact_id).first()
                if contact:
                    contact.display_name = display_name
                    contact.unstructured_profile = profile_data
                    contact.updated_at = datetime.now(timezone.utc)
                    session.commit()
                    return str(contact.id)

            # 2. Check if a contact with the same display_name exists (merge)
            existing = session.query(Contact).filter(Contact.display_name == display_name).first()
            if existing:
                existing.unstructured_profile = profile_data
                existing.updated_at = datetime.now(timezone.utc)
                session.flush()
                db_id = existing.id
            else:
                # 3. Create new contact
                new_contact = Contact(
                    display_name=display_name,
                    unstructured_profile=profile_data,
                )
                session.add(new_contact)
                session.flush()
                db_id = new_contact.id

            # 4. Ensure a linked_account exists
            existing_link = (
                session.query(LinkedAccount)
                .filter(LinkedAccount.provider_id == legacy_contact_id)
                .first()
            )
            if not existing_link:
                link = LinkedAccount(
                    contact_id=db_id,
                    provider=provider,
                    provider_id=legacy_contact_id,
                )
                session.add(link)

            session.commit()
            return str(db_id)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_fact(self, legacy_contact_id: str, fact_index: int) -> bool:
        """Remove a fact by index from the contact's unstructured_profile."""
        session = get_session()
        try:
            linked = (
                session.query(LinkedAccount)
                .filter(LinkedAccount.provider_id == legacy_contact_id)
                .first()
            )
            if not linked:
                return False

            contact = session.query(Contact).filter(Contact.id == linked.contact_id).first()
            if not contact:
                return False

            profile = dict(contact.unstructured_profile) if contact.unstructured_profile else {}
            facts = profile.get("facts", [])
            if 0 <= fact_index < len(facts):
                facts.pop(fact_index)
                profile["facts"] = facts
                profile["last_updated"] = datetime.now(timezone.utc).isoformat()
                contact.unstructured_profile = profile
                contact.updated_at = datetime.now(timezone.utc)
                session.commit()
                return True
            return False
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_contact_profile(self, legacy_contact_id: str, profile_data: Dict[str, Any]) -> bool:
        """Update the full unstructured_profile for a contact identified by legacy ID."""
        session = get_session()
        try:
            linked = (
                session.query(LinkedAccount)
                .filter(LinkedAccount.provider_id == legacy_contact_id)
                .first()
            )
            if not linked:
                return False

            contact = session.query(Contact).filter(Contact.id == linked.contact_id).first()
            if not contact:
                return False

            contact.display_name = profile_data.get("display_name", contact.display_name)
            contact.unstructured_profile = profile_data
            contact.updated_at = datetime.now(timezone.utc)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── Extraction State ────────────────────────────────────────────────

    def get_extraction_state(self) -> int:
        """Read the extraction checkpoint (processed_lines) from the DB.

        Stored as a single-row table or a well-known key in a metadata table.
        For simplicity, we use a contacts-level convention: a special contact
        row with display_name='__extraction_state__'.
        """
        session = get_session()
        try:
            row = session.query(Contact).filter(Contact.display_name == "__extraction_state__").first()
            if row and row.unstructured_profile:
                return row.unstructured_profile.get("processed_lines", 0)
            return 0
        finally:
            session.close()

    def save_extraction_state(self, processed_lines: int) -> None:
        """Persist the extraction checkpoint."""
        session = get_session()
        try:
            row = session.query(Contact).filter(Contact.display_name == "__extraction_state__").first()
            state = {"processed_lines": processed_lines, "updated_at": datetime.now(timezone.utc).isoformat()}
            if row:
                row.unstructured_profile = state
                row.updated_at = datetime.now(timezone.utc)
            else:
                row = Contact(display_name="__extraction_state__", unstructured_profile=state)
                session.add(row)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── Discoveries / Analytics ─────────────────────────────────────────

    def get_shared_intelligence(self) -> List[Dict[str, Any]]:
        """
        Analytic query: Identifies overlapping facts across contacts.
        Same logic as the old DataStore.get_shared_intelligence() but reads from DB.
        """
        all_contacts = self.get_all_contacts()
        shared_map: Dict[tuple, list] = {}

        for profile in all_contacts:
            cid = profile.get("contact_id", "")
            display_name = profile.get("display_name", "")
            if display_name.startswith("__"):
                continue  # Skip metadata rows

            for fact in profile.get("facts", []):
                confidence = fact.get("confidence", "medium")
                if confidence != "high":
                    continue
                category = fact.get("category", "").lower()
                if category in ["identity", "biographical"]:
                    continue

                key = (fact.get("category", ""), fact.get("value", "").strip().lower())
                if key not in shared_map:
                    shared_map[key] = []
                if cid not in [entry["cid"] for entry in shared_map[key]]:
                    shared_map[key].append({"cid": cid, "name": display_name})

        discoveries = []
        for (category, value), entries in shared_map.items():
            if len(entries) > 1:
                discoveries.append({
                    "category": category,
                    "value": value,
                    "connected_profiles": [e["name"] for e in entries],
                    "contact_ids": [e["cid"] for e in entries],
                    "intensity": len(entries),
                })
        return sorted(discoveries, key=lambda x: x["intensity"], reverse=True)

    # ── Helpers ─────────────────────────────────────────────────────────

    def _get_provider_id(self, session, contact_db_id: uuid.UUID) -> Optional[str]:
        """Get the first linked provider_id for a contact."""
        linked = (
            session.query(LinkedAccount)
            .filter(LinkedAccount.contact_id == contact_db_id)
            .first()
        )
        return linked.provider_id if linked else None
