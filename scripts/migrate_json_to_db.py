#!/usr/bin/env python3
"""
Migrate data from data/contacts.json into PostgreSQL.

Usage:
    python scripts/migrate_json_to_db.py

Prerequisites:
    - PostgreSQL running with echo_crm database created
    - Schema applied:  psql -d echo_crm -f db/init_schema.sql
    - DATABASE_URL set in .env
"""

import json
import os
import sys

# Add project root to path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

import config
from db import init_db
from db.repository import ContactRepository


def main():
    contacts_path = config.CONTACTS_FILE
    if not contacts_path.exists():
        print(f"❌ Contacts file not found: {contacts_path}")
        sys.exit(1)

    print(f"📂 Loading contacts from {contacts_path}...")
    with open(contacts_path, "r") as f:
        data = json.load(f)

    contacts = data.get("contacts", {})
    processed_lines = data.get("processed_lines", 0)
    group_chats = data.get("group_chats", {})

    print(f"   Found {len(contacts)} contacts, {len(group_chats)} group chats")
    print(f"   Extraction checkpoint: line {processed_lines}")

    # Ensure tables exist
    print("\n🔧 Ensuring database tables exist...")
    init_db()
    print("   ✓ Tables ready")

    repo = ContactRepository()

    # Migrate contacts
    print(f"\n📥 Migrating {len(contacts)} contacts to PostgreSQL...")
    migrated = 0
    errors = 0

    for contact_id, profile_data in contacts.items():
        display_name = profile_data.get("display_name", "Unknown")
        try:
            # Determine provider from contact_id
            provider = "imsg"
            if contact_id.startswith("imsg##"):
                provider = "imsg"
            elif contact_id.startswith("beeper##"):
                provider = "beeper"

            repo.upsert_contact(
                legacy_contact_id=contact_id,
                display_name=display_name,
                profile_data=profile_data,
                provider=provider,
            )
            migrated += 1

            if migrated % 25 == 0:
                print(f"   ... {migrated}/{len(contacts)} contacts migrated")

        except Exception as e:
            errors += 1
            print(f"   ⚠ Failed to migrate '{display_name}' ({contact_id}): {e}")

    # Save extraction state
    if processed_lines > 0:
        print(f"\n💾 Saving extraction checkpoint: line {processed_lines}")
        repo.save_extraction_state(processed_lines)

    # Summary
    print(f"\n{'='*50}")
    print(f"✅ Migration complete!")
    print(f"   Contacts migrated: {migrated}")
    if errors:
        print(f"   ⚠ Errors: {errors}")
    print(f"   Extraction checkpoint: {processed_lines}")
    print(f"\n   You can verify with:")
    print(f'   psql -d echo_crm -c "SELECT count(*) FROM contacts;"')
    print(f'   psql -d echo_crm -c "SELECT display_name FROM contacts LIMIT 10;"')


if __name__ == "__main__":
    main()
