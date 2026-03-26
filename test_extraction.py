import asyncio
import json
import logging
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import config
from profile_extractor import ProfileExtractor
from models import ContactProfile, Fact

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test-extraction")

class ExtractionTester:
    def __init__(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        logger.info(f"Using temp directory: {self.tmp_dir}")
        
        # Override config paths for testing
        self.old_data_dir = config.DATA_DIR
        config.DATA_DIR = self.tmp_dir
        config.RAW_LOG_FILE = self.tmp_dir / "messages.jsonl"
        config.CONTACTS_FILE = self.tmp_dir / "contacts.json"
        
        # Ensure the test file doesn't exist yet
        if config.RAW_LOG_FILE.exists():
            config.RAW_LOG_FILE.unlink()

    def cleanup(self):
        shutil.rmtree(self.tmp_dir)
        config.DATA_DIR = self.old_data_dir
        logger.info("Cleaned up temp directory.")

    def add_fake_messages(self, messages: list[dict]):
        with open(config.RAW_LOG_FILE, "a") as f:
            for msg in messages:
                f.write(json.dumps(msg) + "\n")

    async def run_test(self, name: str, messages: list[dict], expected_facts: dict[str, list[tuple[str, str]]], 
                       check_no_profiles: list[str] = None,
                       check_temporal: dict[str, list[tuple[str, str]]] = None,
                       check_no_relationships: dict[str, list[str]] = None):
        """
        Run a test case with a clean environment.
        
        Args:
            check_no_profiles: List of display_name strings that should NOT exist as profiles
            check_temporal: Dict of contact_name -> [(category, expected_temporal_status)]
            check_no_relationships: Dict of contact_name -> [relationship_types that should NOT exist]
        """
        logger.info(f"🚀 Running Test: {name}")
        
        # Isolation: Clear log and contacts for each test
        if config.RAW_LOG_FILE.exists():
            config.RAW_LOG_FILE.unlink()
        if config.CONTACTS_FILE.exists():
            config.CONTACTS_FILE.unlink()
        nosql_path = config.DATA_DIR / "echo_nosql.json"
        if nosql_path.exists():
            nosql_path.unlink()
            
        self.add_fake_messages(messages)
        
        extractor = ProfileExtractor()
        await extractor.extract_profiles(force_all=True)
        
        profiles = extractor.get_all_profiles()
        
        errors = []

        # Check expected facts
        for contact_name, expected in expected_facts.items():
            profile = None
            for p in profiles.values():
                if p.display_name.lower() == contact_name.lower():
                    profile = p
                    break
            
            if not profile:
                errors.append(f"❌ Could not find profile for '{contact_name}'")
                continue
            
            actual_facts = [(f.category, f.value) for f in profile.facts]
            
            for exp_cat, exp_val in expected:
                found = False
                for act_cat, act_val in actual_facts:
                    if act_cat.lower() == exp_cat.lower() and exp_val.lower() in act_val.lower():
                        found = True
                        break
                
                if not found:
                    errors.append(f"❌ Missing fact for {contact_name}: Category='{exp_cat}', Value containing='{exp_val}'")
                    errors.append(f"   Actual facts: {actual_facts}")

        # Check that certain profiles do NOT exist (group chat names)
        if check_no_profiles:
            for bad_name in check_no_profiles:
                for p in profiles.values():
                    if p.display_name.lower() == bad_name.lower():
                        errors.append(f"❌ Profile should NOT exist for group name '{bad_name}'")

        # Check temporal status
        if check_temporal:
            for contact_name, expected_temporal in check_temporal.items():
                profile = None
                for p in profiles.values():
                    if p.display_name.lower() == contact_name.lower():
                        profile = p
                        break
                if not profile:
                    errors.append(f"❌ Could not find profile for temporal check: '{contact_name}'")
                    continue
                for exp_cat, exp_status in expected_temporal:
                    found = False
                    for f in profile.facts:
                        if f.category.lower() == exp_cat.lower() and f.temporal_status == exp_status:
                            found = True
                            break
                    if not found:
                        actual_temporal = [(f.category, f.value, f.temporal_status) for f in profile.facts]
                        errors.append(f"❌ Missing temporal status for {contact_name}: Category='{exp_cat}', Expected status='{exp_status}'")
                        errors.append(f"   Actual: {actual_temporal}")

        # Check that certain relationship types do NOT exist
        if check_no_relationships:
            for contact_name, banned_types in check_no_relationships.items():
                profile = None
                for p in profiles.values():
                    if p.display_name.lower() == contact_name.lower():
                        profile = p
                        break
                if profile:
                    for rel in profile.relationships:
                        if rel.type.lower() in [t.lower() for t in banned_types]:
                            errors.append(f"❌ Relationship type '{rel.type}' should NOT exist for {contact_name} → {rel.target_name}")

        if not errors:
            logger.info(f"✅ Test '{name}' PASSED")
            return True
        else:
            logger.error(f"💥 Test '{name}' FAILED:")
            for err in errors:
                logger.error(f"  {err}")
            return False

async def main():
    tester = ExtractionTester()
    try:
        # --- Test Case 1: Basic Extraction & Attribution ---
        case1_msgs = [
            {
                "chat_id": "chat_alice",
                "chat_name": "Alice",
                "sender_id": "alice_123",
                "sender_name": "Alice",
                "is_self": False,
                "chat_type": "single",
                "text": "Hey! I just started a new job as a Product Manager at Figma. I'm living in Brooklyn now.",
                "timestamp": "2024-03-20T10:00:00Z"
            },
            {
                "chat_id": "chat_alice",
                "chat_name": "Alice",
                "sender_id": "me",
                "sender_name": config.MY_NAME,
                "is_self": True,
                "chat_type": "single",
                "text": "Congrats Alice! I'm still a Software Engineer at Google, but I moved to Austin last month.",
                "timestamp": "2024-03-20T10:05:00Z"
            }
        ]
        case1_expected = {
            "Alice": [("Professional", "Product Manager"), ("Professional", "Figma"), ("Biographical", "Brooklyn")],
            config.MY_NAME: [("Professional", "Software Engineer"), ("Professional", "Google"), ("Biographical", "Austin")]
        }
        
        # --- Test Case 2: Temporal Status ---
        # Message from 2 years ago — sick -> should be past
        case2_msgs = [
            {
                "chat_id": "chat_bob",
                "chat_name": "Bob Smith",
                "sender_id": "bob_456",
                "sender_name": "Bob Smith",
                "is_self": False,
                "chat_type": "single",
                "text": "I'm so sick right now, been in bed all week with the flu.",
                "timestamp": "2024-03-18T15:00:00Z"
            },
            {
                "chat_id": "chat_bob",
                "chat_name": "Bob Smith",
                "sender_id": "bob_456",
                "sender_name": "Bob Smith",
                "is_self": False,
                "chat_type": "single",
                "text": "I work at Microsoft as a Senior Engineer.",
                "timestamp": "2024-03-18T15:05:00Z"
            }
        ]
        case2_expected = {
            "Bob Smith": [("Biographical", "sick"), ("Professional", "Microsoft")],
        }
        case2_temporal = {
            "Bob Smith": [("Biographical", "past")],  # Sick from 2 years ago should be past
        }

        # --- Test Case 3: Relationship Conservatism ---
        # Single casual mention should NOT produce "brother" or "significant_other"
        case3_msgs = [
            {
                "chat_id": "chat_carol",
                "chat_name": "Carol",
                "sender_id": "carol_789",
                "sender_name": "Carol",
                "is_self": False,
                "chat_type": "single",
                "text": "I ran into Jake at the store yesterday, he said hi.",
                "timestamp": "2026-03-20T10:00:00Z"
            }
        ]
        case3_expected = {
            "Carol": [],
        }
        case3_no_rels = {
            "Carol": ["family", "significant_other", "brother", "sister"],
        }

        # --- Test Case 4: Group Chat Handling ---
        case4_msgs = [
            {
                "chat_id": "group_123",
                "chat_name": "Alice, Bob & Carol",
                "sender_id": "alice_123",
                "sender_name": "Alice",
                "is_self": False,
                "chat_type": "group",
                "text": "I just got promoted to VP at work!",
                "timestamp": "2026-03-20T10:00:00Z"
            },
            {
                "chat_id": "group_123",
                "chat_name": "Alice, Bob & Carol",
                "sender_id": "bob_456",
                "sender_name": "Bob",
                "is_self": False,
                "chat_type": "group",
                "text": "I'm moving to Denver next month for a new role at Salesforce.",
                "timestamp": "2026-03-20T10:05:00Z"
            },
            {
                "chat_id": "group_123",
                "chat_name": "Alice, Bob & Carol",
                "sender_id": "me",
                "sender_name": config.MY_NAME,
                "is_self": True,
                "chat_type": "group",
                "text": "That's awesome! Congrats to both of you!",
                "timestamp": "2026-03-20T10:10:00Z"
            }
        ]
        case4_expected = {
            "Alice": [("Professional", "Vice President")],
            "Bob": [("Biographical", "Denver")],
        }
        case4_no_profiles = ["Alice, Bob & Carol"]  # Group name should NOT be a profile

        # --- Test Case 5: Slang & Complex Inference ---
        case5_msgs = [
            {
                "chat_id": "chat_dave", "chat_name": "Dave", "sender_name": "Dave", "is_self": False,
                "chat_type": "single",
                "text": "Yo, my old man (Bill) just retired from the FDNY after 30 years.", 
                "timestamp": "2024-03-25T11:00:00Z"
            }
        ]
        case5_expected = {
            "Bill": [("Professional", "FDNY"), ("Professional", "Retired")]
        }

        # Run tests
        results = []
        results.append(await tester.run_test("Basic & Attribution", case1_msgs, case1_expected))
        results.append(await tester.run_test("Temporal Status (Past Tense)", case2_msgs, case2_expected, check_temporal=case2_temporal))
        results.append(await tester.run_test("Relationship Conservatism", case3_msgs, case3_expected, check_no_relationships=case3_no_rels))
        results.append(await tester.run_test("Group Chat Handling", case4_msgs, case4_expected, check_no_profiles=case4_no_profiles))
        results.append(await tester.run_test("Slang & Inference", case5_msgs, case5_expected))

        passed = sum(results)
        total = len(results)
        logger.info(f"\n{'='*50}")
        logger.info(f"Results: {passed}/{total} tests passed")
        if passed == total:
            logger.info("🎉 All tests passed!")
        else:
            logger.error(f"💥 {total - passed} test(s) failed")

    finally:
        tester.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
