"""
Message Logger — syncs Beeper messages to a local JSONL file.

Responsibilities:
  - Enumerate all chats from Beeper Desktop API
  - Paginate through message history for each chat
  - Append new messages to a JSONL log file (one JSON object per line)
  - Track sync cursors so subsequent runs only fetch new messages

The raw log is the single source of truth; the profile extractor reads from it.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from beeper_client import BeeperClient
import config

logger = logging.getLogger(__name__)


class SyncState:
    """Persists per-chat sync cursors so we only fetch new messages."""

    def __init__(self, path: Path = config.SYNC_STATE_FILE):
        self._path = path
        self._state: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            with open(self._path) as f:
                return json.load(f)
        return {"chats": {}, "last_full_sync": None}

    def save(self):
        with open(self._path, "w") as f:
            json.dump(self._state, f, indent=2)

    def get_newest_cursor(self, chat_id: str) -> str | None:
        """Get the newest cursor from last sync to fetch only newer messages."""
        return self._state["chats"].get(chat_id, {}).get("newest_cursor")

    def set_cursors(self, chat_id: str, newest: str, oldest: str, message_count: int):
        self._state["chats"][chat_id] = {
            "newest_cursor": newest,
            "oldest_cursor": oldest,
            "message_count": message_count,
            "last_synced": datetime.now(timezone.utc).isoformat(),
        }

    def mark_full_sync(self):
        self._state["last_full_sync"] = datetime.now(timezone.utc).isoformat()

    @property
    def has_done_initial_sync(self) -> bool:
        return self._state.get("last_full_sync") is not None


class MessageLogger:
    """
    Syncs messages from Beeper to a local JSONL log file.

    Each line in the log is a JSON object:
    {
        "chat_id": "...",
        "chat_name": "...",
        "chat_type": "single" | "group",
        "message_id": "...",
        "sender_name": "...",
        "sender_id": "...",
        "timestamp": "...",
        "text": "...",
        "is_self": true/false,
        "synced_at": "..."
    }
    """

    def __init__(self, client: BeeperClient):
        self._client = client
        self._sync_state = SyncState()
        self._seen_ids: set[str] = self._load_seen_ids()

    def _load_seen_ids(self) -> set[str]:
        """Load already-logged message IDs to avoid duplicates."""
        seen = set()
        if config.RAW_LOG_FILE.exists():
            with open(config.RAW_LOG_FILE) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if "message_id" in record:
                            seen.add(record["message_id"])
                    except json.JSONDecodeError:
                        continue
        logger.info(f"Loaded {len(seen)} existing message IDs from log")
        return seen

    def sync_all(self, limit_chats: int = None, limit_messages: int = None) -> int:
        """
        Sync messages from all chats. Returns total new messages logged.

        On first run, fetches full history (up to MAX_MESSAGES_PER_CHAT per chat).
        On subsequent runs, only fetches messages newer than the last sync cursor.
        """
        total_new = 0

        # Fetch all chats with pagination
        all_chats = self._fetch_all_chats()
        logger.info(f"Found {len(all_chats)} chats to sync")
        
        if limit_chats:
            all_chats = all_chats[:limit_chats]
            logger.info(f"  Limiting sync to first {len(all_chats)} chats for testing")

        for chat in all_chats:
            chat_id = chat.get("id", "")
            chat_name = chat.get("title", "Unknown")
            chat_type = chat.get("type", "unknown")

            if not config.INCLUDE_GROUP_CHATS and chat_type == "group":
                logger.debug(f"Skipping group chat: {chat_name}")
                continue

            try:
                new_count = self._sync_chat(chat_id, chat_name, chat_type, limit_messages=limit_messages)
                total_new += new_count
                if new_count > 0:
                    logger.info(f"  [{chat_name}] +{new_count} messages")
            except Exception as e:
                logger.error(f"  [{chat_name}] Error syncing: {e}")

        self._sync_state.mark_full_sync()
        self._sync_state.save()

        logger.info(
            f"Sync complete: {total_new} new messages across {len(all_chats)} chats"
        )
        return total_new

    def _fetch_all_chats(self) -> list[dict[str, Any]]:
        """Paginate through all chats."""
        all_chats: list[dict[str, Any]] = []
        cursor = None

        while True:
            resp = self._client.list_chats(limit=200, cursor=cursor)
            items = resp.get("items", [])
            if not items:
                break

            all_chats.extend(items)

            # Check for next page
            has_more = resp.get("hasMore", False)
            if not has_more:
                break

            oldest_cursor = resp.get("oldestCursor")
            if not oldest_cursor or oldest_cursor == cursor:
                break
            cursor = oldest_cursor

        return all_chats

    def _sync_chat(self, chat_id: str, chat_name: str, chat_type: str, limit_messages: int = None) -> int:
        """Sync messages for a single chat. Returns count of new messages."""
        new_messages: list[dict[str, Any]] = []
        messages_fetched = 0

        # Use passed limit or default
        max_limit = limit_messages if limit_messages is not None else config.MAX_MESSAGES_PER_CHAT

        # If we have a previous cursor, fetch only newer messages
        saved_cursor = self._sync_state.get_newest_cursor(chat_id)
        cursor = saved_cursor
        direction = "after" if saved_cursor else None

        newest_cursor = None
        oldest_cursor = None

        while messages_fetched < max_limit:
            try:
                resp = self._client.list_messages(
                    chat_id=chat_id, cursor=cursor, direction=direction
                )
            except Exception as e:
                logger.warning(f"Failed to fetch messages for {chat_name}: {e}")
                break

            items = resp.get("items", [])
            if not items:
                break

            # The Beeper API for messages doesn't always return top-level cursors
            # Fall back to sortKey of the first/last message in the array
            if not newest_cursor:
                newest_cursor = resp.get("newestCursor")
                if not newest_cursor and items:
                    newest_cursor = items[0].get("sortKey")
            
            oldest_cursor = resp.get("oldestCursor")
            if not oldest_cursor and items:
                oldest_cursor = items[-1].get("sortKey")

            for msg in items:
                msg_id = msg.get("id", "")
                if msg_id in self._seen_ids:
                    continue

                record = self._message_to_record(msg, chat_id, chat_name, chat_type)
                if record:
                    new_messages.append(record)
                    self._seen_ids.add(msg_id)

            messages_fetched += len(items)

            # Pagination: keep going if there are more
            has_more = resp.get("hasMore", False)
            if not has_more:
                break

            next_cursor = oldest_cursor
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
            # After first request, always paginate backward (older)
            if not direction:
                direction = "before"

        # Append to log file
        if new_messages:
            self._append_to_log(new_messages)

            # Update sync state
            if newest_cursor:
                self._sync_state.set_cursors(
                    chat_id,
                    newest=newest_cursor,
                    oldest=oldest_cursor or "",
                    message_count=messages_fetched,
                )

        return len(new_messages)

    def _message_to_record(
        self, msg: dict[str, Any], chat_id: str, chat_name: str, chat_type: str
    ) -> dict[str, Any] | None:
        """Convert a Beeper message object to a log record."""
        text = msg.get("text", "")
        if not text:
            # Skip media-only or system messages without text
            return None

        import mac_contacts

        sender_id = msg.get("senderID", "")
        sender_name = msg.get("senderName", "Unknown")
        resolved_sender_name = mac_contacts.resolve_contact(sender_id, sender_name)
        if resolved_sender_name == "Unknown" and sender_name != "Unknown":
            resolved_sender_name = mac_contacts.resolve_contact(sender_name, sender_name)
            
        resolved_chat_name = mac_contacts.resolve_contact(chat_name, chat_name)
        
        return {
            "chat_id": chat_id,
            "chat_name": resolved_chat_name,
            "chat_type": chat_type,
            "message_id": msg.get("id", ""),
            "sender_name": resolved_sender_name,
            "sender_id": sender_id,
            "is_self": msg.get("isSender", False),
            "timestamp": msg.get("timestamp", ""),
            "text": text,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

    def _append_to_log(self, records: list[dict[str, Any]]):
        """Append message records to the JSONL log file."""
        with open(config.RAW_LOG_FILE, "a") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
