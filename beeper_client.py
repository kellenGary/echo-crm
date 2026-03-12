"""
Beeper Desktop API client.

Handles all communication with the Beeper Desktop REST API.
Single Responsibility: HTTP transport + response parsing for Beeper endpoints.
"""

from urllib.parse import quote

import httpx
from typing import Any

import config


class BeeperClient:
    """Thin client for the Beeper Desktop REST API (v1)."""

    def __init__(
        self,
        base_url: str = config.BEEPER_BASE_URL,
        token: str = config.BEEPER_API_TOKEN,
        timeout: float = 30.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------
    def list_accounts(self) -> list[dict[str, Any]]:
        """Return all connected messaging accounts."""
        resp = self._client.get("/v1/accounts")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Chats
    # ------------------------------------------------------------------
    def list_chats(
        self,
        limit: int = 50,
        chat_type: str | None = None,
        unread_only: bool = False,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """
        List chats ordered by last activity.

        Response shape:
        {
            "items": [...],
            "hasMore": bool,
            "oldestCursor": str,
            "newestCursor": str
        }
        """
        params: dict[str, Any] = {"limit": limit}
        if chat_type:
            params["type"] = chat_type
        if unread_only:
            params["unreadOnly"] = "true"
        if cursor:
            params["cursor"] = cursor

        resp = self._client.get("/v1/chats", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_chat(self, chat_id: str) -> dict[str, Any]:
        """Get details for a specific chat."""
        encoded_id = quote(chat_id, safe="")
        resp = self._client.get(f"/v1/chats/{encoded_id}")
        resp.raise_for_status()
        return resp.json()

    def search_chats(self, query: str, limit: int = 20) -> dict[str, Any]:
        """Search chats by name/participant."""
        resp = self._client.get(
            "/v1/chats/search", params={"query": query, "limit": limit}
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------
    def list_messages(
        self,
        chat_id: str,
        cursor: str | None = None,
        direction: str | None = None,
    ) -> dict[str, Any]:
        """
        List messages in a chat with pagination.

        Response shape:
        {
            "items": [
                {
                    "id": str,
                    "chatID": str,
                    "senderID": str,
                    "senderName": str,
                    "timestamp": str (ISO 8601),
                    "sortKey": str,
                    "text": str,
                    "isSender": bool (true = sent by authenticated user),
                    ...
                }
            ],
            "hasMore": bool,
            "oldestCursor": str,
            "newestCursor": str
        }
        """
        encoded_id = quote(chat_id, safe="")
        params: dict[str, Any] = {}
        if cursor:
            params["cursor"] = cursor
        if direction:
            params["direction"] = direction

        resp = self._client.get(f"/v1/chats/{encoded_id}/messages", params=params)
        resp.raise_for_status()
        return resp.json()

    def search_messages(
        self,
        query: str | None = None,
        chat_ids: list[str] | None = None,
        limit: int = 50,
        date_after: str | None = None,
        date_before: str | None = None,
    ) -> dict[str, Any]:
        """Search messages across chats."""
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        if chat_ids:
            params["chatIDs"] = chat_ids
        if date_after:
            params["dateAfter"] = date_after
        if date_before:
            params["dateBefore"] = date_before

        resp = self._client.get("/v1/messages/search", params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------
    def send_message(
        self,
        chat_id: str,
        text: str,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send a text message to a chat. Supports markdown."""
        encoded_id = quote(chat_id, safe="")
        body: dict[str, Any] = {"text": text}
        if reply_to:
            body["replyToMessageID"] = reply_to

        resp = self._client.post(f"/v1/chats/{encoded_id}/messages", json=body)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
