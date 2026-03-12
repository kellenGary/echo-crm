"""
Chat Bot — watches the "Note to self" chat and replies with contact intelligence.

Responsibilities:
  - Poll the Note to self chat for new messages
  - When a new message arrives, treat it as a query
  - Run the query through the QueryEngine
  - Reply with the answer in the same chat

This lets you ask questions about your contacts from your phone via Beeper.

Supported queries (plain questions work too):
  /contacts — List known contacts
  /sync     — Trigger a fresh message sync + extraction
  /help     — Show usage instructions
  Anything else is treated as a question about your contacts.
"""

import logging
import time
from typing import Any

from beeper_client import BeeperClient
from query_engine import QueryEngine
import config

logger = logging.getLogger(__name__)

# Prefix added to all bot replies so we can distinguish them from user queries.
# Since Note to self only has one participant, isSender is always True.
BOT_REPLY_PREFIX = "🤖💬 "

HELP_TEXT = """**Beeper Contact Intelligence Bot**

**Ask me anything about your contacts!**

Examples:
• `Where does John work?`
• `When is Sarah's birthday?`
• `What do I know about Mike?`

Commands:
• `/contacts` — List all known contacts
• `/sync` — Sync latest messages from all chats
• `/help` — Show this help message

Just type your question and I'll search your chat history and contact profiles."""


class ChatBot:
    """
    Watches the Note to self chat in Beeper and responds
    to queries about contacts using the local LLM.
    """

    def __init__(self):
        self._client = BeeperClient()
        self._engine = QueryEngine()
        self._chat_id = config.NOTE_TO_SELF_CHAT_ID
        self._last_seen_sort_key: str | None = None
        self._bot_message_ids: set[str] = set()

    def _initialize_last_seen(self):
        """Set the last seen sort key to the latest message so we
        don't process old messages on startup."""
        try:
            resp = self._client.list_messages(self._chat_id)
            items = resp.get("items", [])
            if items:
                # Items are newest-first; take the newest sortKey
                self._last_seen_sort_key = items[0].get("sortKey")
                logger.info(
                    f"Initialized — ignoring messages up to sortKey: "
                    f"{self._last_seen_sort_key}"
                )
            else:
                self._last_seen_sort_key = "0"
        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            self._last_seen_sort_key = "0"

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------
    def run(self):
        """Main polling loop — watches for new messages and replies."""
        self._initialize_last_seen()

        print("\n🤖 Bot is running! Send a message to 'Note to self' in Beeper.")
        print(f"   Polling every {config.BOT_POLL_INTERVAL}s. Ctrl+C to stop.\n")

        while True:
            try:
                self._poll_once()
            except KeyboardInterrupt:
                logger.info("Bot stopped.")
                break
            except Exception as e:
                logger.error(f"Poll error: {e}")
            time.sleep(config.BOT_POLL_INTERVAL)

    def _poll_once(self):
        """Check for new messages in Note to self."""
        try:
            resp = self._client.list_messages(self._chat_id)
        except Exception as e:
            logger.debug(f"Failed to fetch messages: {e}")
            return

        items = resp.get("items", [])
        if not items:
            return

        # Collect new messages from the user (newest-first in the API)
        new_messages = []
        for msg in items:
            sort_key = msg.get("sortKey", "0")
            msg_id = msg.get("id", "")

            # Skip bot's own replies
            if msg_id in self._bot_message_ids:
                continue

            # Skip already-processed messages
            if (
                self._last_seen_sort_key
                and sort_key <= self._last_seen_sort_key
            ):
                continue

            # Only process user-sent messages with text
            text = msg.get("text", "").strip()
            if not text:
                continue

            # Skip bot's own replies (identified by prefix)
            if text.startswith(BOT_REPLY_PREFIX):
                continue

            new_messages.append(msg)

        if not new_messages:
            return

        # Update last seen to the newest sortKey
        all_sort_keys = [m.get("sortKey", "0") for m in new_messages]
        self._last_seen_sort_key = max(all_sort_keys)

        # Process each new message (oldest first for proper ordering)
        new_messages.reverse()
        for msg in new_messages:
            text = msg.get("text", "").strip()
            msg_id = msg.get("id", "")

            logger.info(f"Received query: {text}")
            response = self._process_query(text)
            self._send_reply(response, msg_id)

    # ------------------------------------------------------------------
    # Query processing
    # ------------------------------------------------------------------
    def _process_query(self, text: str) -> str:
        """Route a user message to the appropriate handler."""
        text_lower = text.lower().strip()

        # Commands
        if text_lower in ("/help", "help"):
            return HELP_TEXT

        if text_lower in ("/contacts", "contacts", "/list"):
            return self._handle_contacts_command()

        if text_lower in ("/sync", "sync"):
            return self._handle_sync_command()

        # Strip optional "?" prefix
        if text_lower.startswith("?"):
            text = text[1:].strip()

        # Run through query engine
        try:
            return self._engine.ask(text)
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return f"❌ Sorry, something went wrong: {e}"

    def _handle_contacts_command(self) -> str:
        """Format contact list for chat display."""
        contacts = self._engine.list_contacts()
        if not contacts:
            return "No contacts extracted yet. Send `/sync` first."

        lines = ["**📇 Known Contacts**\n"]
        for c in contacts[:20]:
            name = c["name"]
            facts = c["facts"]
            msgs = c["messages"]
            lines.append(f"• **{name}** — {facts} facts, {msgs} msgs")

        if len(contacts) > 20:
            lines.append(f"\n_...and {len(contacts) - 20} more_")

        return "\n".join(lines)

    def _handle_sync_command(self) -> str:
        """Run a message sync + indexing + extraction."""
        try:
            from main import cmd_sync, cmd_index, cmd_extract

            # Run sync
            cmd_sync()
            # Run indexing (new!)
            cmd_index()
            # Run extraction
            cmd_extract()

            # Refresh query engine with new data
            self._engine = QueryEngine()

            return "✅ Sync, indexing, and extraction complete!"
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return f"❌ Sync failed: {e}"

    def _send_reply(self, text: str, reply_to_id: str | None = None):
        """Send a reply in the Note to self chat."""
        try:
            result = self._client.send_message(
                chat_id=self._chat_id,
                text=BOT_REPLY_PREFIX + text,
                reply_to=reply_to_id,
            )
            # Track bot message IDs so we don't process our own replies
            bot_msg_id = result.get("id", "")
            if bot_msg_id:
                self._bot_message_ids.add(bot_msg_id)
            logger.info("Reply sent ✓")
        except Exception as e:
            logger.error(f"Failed to send reply: {e}")

    def close(self):
        self._client.close()
