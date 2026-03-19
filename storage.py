import json
from pathlib import Path
from typing import Dict, List, Optional
from tinydb import TinyDB, Query
from models import ContactProfile

class DataStore:
    """A NoSQL-style abstraction for Echo CRM profiles."""
    
    def __init__(self, db_path: Path):
        self.db = TinyDB(db_path)
        self.contacts = self.db.table('contacts')

    def save_profile(self, profile: ContactProfile):
        """Save or update a contact profile."""
        Contact = Query()
        profile_data = profile.model_dump()
        self.contacts.upsert(profile_data, Contact.contact_id == profile.contact_id)

    def get_profile(self, contact_id: str) -> Optional[ContactProfile]:
        """Retrieve a specific profile."""
        Contact = Query()
        result = self.contacts.get(Contact.contact_id == contact_id)
        if result:
            return ContactProfile.model_validate(result)
        return None

    def get_all_profiles(self) -> Dict[str, ContactProfile]:
        """Retrieve all profiles indexed by ID."""
        all_data = self.contacts.all()
        return {item['contact_id']: ContactProfile.model_validate(item) for item in all_data}

    def search_by_fact(self, fact_value: str) -> List[ContactProfile]:
        """NoSQL discovery query: find all people associated with a fact value."""
        # Simple implementation using TinyDB
        results = []
        for item in self.contacts.all():
            for fact in item.get('facts', []):
                if fact_value.lower() in fact['value'].lower():
                    results.append(ContactProfile.model_validate(item))
                    break
        return results

    def get_shared_intelligence(self) -> List[dict]:
        """
        Analytic query: Identifies overlapping facts across different profiles.
        Detects 'Hidden Connections' where two or more people share a specific 
        and high-confidence fact (e.g., same location, company, or niche interest).
        """
        shared_map = {} # (category, value) -> [contact_ids]
        
        all_profiles = self.get_all_profiles()
        for cid, profile in all_profiles.items():
            for fact in profile.facts:
                if fact.confidence != "high": continue
                if fact.category.lower() in ["identity", "biographical"]: continue # Skip generic bio info
                
                key = (fact.category, fact.value.strip().lower())
                if key not in shared_map:
                    shared_map[key] = []
                if cid not in shared_map[key]:
                    shared_map[key].append(cid)
        
        # Filter for overlaps
        discoveries = []
        for (category, value), cids in shared_map.items():
            if len(cids) > 1:
                discoveries.append({
                    "category": category,
                    "value": value,
                    "connected_profiles": [all_profiles[c].display_name for c in cids],
                    "contact_ids": cids,
                    "intensity": len(cids)
                })
        
        return sorted(discoveries, key=lambda x: x['intensity'], reverse=True)
