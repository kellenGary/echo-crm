"""
Echo CRM

A personal CRM powered by your chat history. Syncs messages from Beeper,
extracts contact profiles using a local LLM, and lets you query for
personal details about your contacts.

Usage:
    python main.py sync        Sync messages from Beeper to local log
    python main.py extract     Run LLM extraction on new messages
    python main.py ask         Interactive Q&A about your contacts
    python main.py contacts    List all known contacts
    python main.py run         Full pipeline: sync → extract → ask
    python main.py daemon      Run sync + extract on a loop (background)
    python main.py bot         Start the Note to self chatbot
    python main.py obsidian    Generate interlinked Obsidian notes
"""

import argparse
import asyncio
import logging
import sys
import time

import config
from beeper_client import BeeperClient
from message_logger import MessageLogger
from profile_extractor import ProfileExtractor
from query_engine import QueryEngine

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)-18s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("echo-crm")


# ── Commands ─────────────────────────────────────────────────────────

def cmd_sync() -> int:
    """Sync messages from Beeper Desktop API to local JSONL log."""
    logger.info("Starting message sync from Beeper...")
    with BeeperClient() as client:
        # Quick connectivity check
        try:
            accounts = client.list_accounts()
            networks = [a.get("network", "?") for a in accounts]
            logger.info(f"Connected accounts: {', '.join(networks)}")
        except Exception as e:
            logger.error(f"Cannot reach Beeper Desktop API: {e}")
            logger.error("Make sure Beeper Desktop is running with the API enabled.")
            return 1

        ml = MessageLogger(client)
        new_count = ml.sync_all()
        logger.info(f"✓ Sync complete — {new_count} new messages logged")
        logger.info(f"  Log file: {config.RAW_LOG_FILE}")
    return 0


def cmd_extract() -> int:
    """Run LLM profile extraction on new messages."""
    logger.info("Starting profile extraction with Ollama...")
    logger.info(f"  Model: {config.OLLAMA_MODEL}")

    extractor = ProfileExtractor()
    updated = extractor.extract_profiles()
    logger.info(f"✓ Extraction complete — {updated} contacts updated")
    logger.info(f"  Profiles: {config.CONTACTS_FILE}")
    return 0


def cmd_ask():
    """Interactive Q&A loop."""
    engine = QueryEngine()

    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║                  Echo CRM — Ask Mode                    ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print("║  Ask anything about your contacts.                      ║")
    print("║  Examples:                                              ║")
    print("║    • Where does John work?                              ║")
    print("║    • When is Sarah's birthday?                          ║")
    print("║    • What do I know about Mike?                         ║")
    print("║    • Who lives in New York?                             ║")
    print("║                                                         ║")
    print("║  Type 'quit' or Ctrl+C to exit.                         ║")
    print("╚══════════════════════════════════════════════════════════╝\n")

    while True:
        try:
            question = input("❓ ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        print("🔍 Searching...")
        answer = engine.ask(question)
        print(f"\n💡 {answer}\n")


def cmd_contacts():
    """List all known contacts."""
    engine = QueryEngine()
    contacts = engine.list_contacts()

    if not contacts:
        print("No contacts extracted yet. Run: python main.py sync && python main.py extract")
        return

    print(f"\n{'Name':<30} {'Facts':>6} {'Messages':>9}  Last Updated")
    print("─" * 75)
    for c in contacts:
        updated = c["last_updated"][:10] if c["last_updated"] else "never"
        print(f"{c['name']:<30} {c['facts']:>6} {c['messages']:>9}  {updated}")
    print(f"\nTotal: {len(contacts)} contacts")


def cmd_run():
    """Full pipeline: sync → extract → ask."""
    if cmd_sync() != 0:
        return
    cmd_extract()
    cmd_ask()


def cmd_daemon():
    """Run sync + extract on a loop."""
    logger.info(
        f"Starting daemon (sync every {config.SYNC_INTERVAL_SECONDS}s)... "
        f"Press Ctrl+C to stop."
    )

    while True:
        try:
            cmd_sync()
            cmd_extract()
            logger.info(
                f"Sleeping {config.SYNC_INTERVAL_SECONDS}s until next sync..."
            )
            time.sleep(config.SYNC_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            logger.info("Daemon stopped.")
            break


def cmd_bot():
    """Start the Note to self chatbot."""
    from chat_bot import ChatBot

    logger.info("Starting Note to self chatbot...")
    bot = ChatBot()

    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║                  Echo CRM — Bot Mode                    ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print("║  Send a message to 'Note to self' in Beeper to query.   ║")
    print("║  Try: 'Where does John work?' or '/help'                ║")
    print("║                                                         ║")
    print("║  Press Ctrl+C to stop.                                  ║")
    print("╚══════════════════════════════════════════════════════════╝\n")

    try:
        bot.run()
    finally:
        bot.close()


def cmd_obsidian():
    """Generate interlinked Obsidian vault notes."""
    from obsidian_writer import ObsidianWriter

    logger.info("Generating Obsidian notes...")
    logger.info(f"  Vault: {config.OBSIDIAN_BEEPER_DIR}")

    writer = ObsidianWriter()
    counts = writer.generate_all()

    print(f"\n✅ Obsidian notes generated!")
    print(f"   👤 {counts['people']} people notes")
    print(f"   📍 {counts['places']} place notes")
    print(f"   💡 {counts['topics']} topic notes")
    print(f"\n   Open Obsidian and check 'Beeper Intelligence/'")
    print(f"   Use Graph View to explore connections!\n")


# ── Entry point ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Echo CRM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "command",
        choices=["sync", "extract", "ask", "contacts", "run", "daemon", "bot", "obsidian"],
        help="Command to run",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    commands = {
        "sync": cmd_sync,
        "extract": cmd_extract,
        "ask": cmd_ask,
        "contacts": cmd_contacts,
        "run": cmd_run,
        "daemon": cmd_daemon,
        "bot": cmd_bot,
        "obsidian": cmd_obsidian,
    }

    result = commands[args.command]()
    if isinstance(result, int):
        sys.exit(result)


if __name__ == "__main__":
    main()
