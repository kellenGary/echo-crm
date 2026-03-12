"""
Query Engine — interactive CLI for asking questions about your contacts.

Responsibilities:
  - Accept natural language questions about contacts
  - Look up relevant context from contact profiles AND raw message logs
  - Send context + question to Ollama for a grounded answer

Two-tier retrieval:
  1. Fast path: Check extracted contact profiles first
  2. Deep path: Search raw message log for additional context
"""

import json
import logging
from typing import Any

import httpx

import config
from profile_extractor import ProfileExtractor

logger = logging.getLogger(__name__)

QUERY_PROMPT = """\
You are a helpful personal assistant with access to the user's chat history. \
Answer the user's question based ONLY on the information provided below. \
If you don't have enough information, say so honestly.

## Contact Profiles
{profiles_context}

## Relevant Messages
{messages_context}

---
**User's question:** {question}

Answer concisely and cite specific messages or facts when possible.
"""


class QueryEngine:
    """
    Answers natural language questions about contacts using
    extracted profiles and raw message history.
    """

    def __init__(self):
        self._ollama_url = config.OLLAMA_BASE_URL
        self._model = config.OLLAMA_MODEL
        self._extractor = ProfileExtractor()

    def ask(self, question: str) -> str:
        """Answer a question about contacts using profiles + message history."""
        # 1. Gather relevant contact profiles
        profiles_context = self._get_relevant_profiles(question)

        # 2. Search raw messages for additional context
        messages_context = self._search_raw_messages(question)

        if not profiles_context and not messages_context:
            return (
                "I don't have any relevant information to answer that question. "
                "Try running a sync first with: python main.py sync"
            )

        # 3. Send to LLM
        prompt = QUERY_PROMPT.format(
            profiles_context=profiles_context or "No matching profiles found.",
            messages_context=messages_context or "No relevant messages found.",
            question=question,
        )

        return self._call_ollama(prompt)

    def _get_relevant_profiles(self, question: str) -> str:
        """Find contact profiles relevant to the question."""
        profiles = self._extractor.get_all_profiles()
        if not profiles:
            return ""

        # Simple keyword matching — check if any contact name appears in the question
        question_lower = question.lower()
        relevant: list[str] = []

        for profile in profiles.values():
            name_lower = profile.display_name.lower()
            # Check if contact name (or part of it) appears in the question
            name_parts = name_lower.split()
            if any(part in question_lower for part in name_parts if len(part) > 2):
                relevant.append(self._format_profile(profile))
            elif not relevant:
                # If no name match, include all profiles as context
                # (the LLM can figure out relevance)
                pass

        # If no specific match, include all profiles (for general questions)
        if not relevant:
            for profile in profiles.values():
                relevant.append(self._format_profile(profile))

        return "\n\n".join(relevant[:10])  # Limit to 10 profiles for context window

    def _format_profile(self, profile) -> str:
        """Format a contact profile for the LLM prompt."""
        lines = [f"### {profile.display_name}"]
        lines.append(f"Messages analyzed: {profile.message_count}")

        if profile.facts:
            for fact in profile.facts:
                confidence = fact.get("confidence", "unknown")
                category = fact.get("category", "Other")
                value = fact.get("value", "")
                source = fact.get("source_quote", "")
                line = f"- **{category}**: {value} (confidence: {confidence})"
                if source:
                    line += f' — _"{source}"_'
                lines.append(line)
        else:
            lines.append("- No extracted facts yet")

        return "\n".join(lines)

    def _search_raw_messages(self, question: str, max_results: int = 30) -> str:
        """Search the raw message log for messages relevant to the question."""
        if not config.RAW_LOG_FILE.exists():
            return ""

        # Extract potential search keywords from the question
        # Filter out common stop words
        stop_words = {
            "what", "where", "when", "who", "how", "does", "did", "is", "are",
            "was", "were", "the", "a", "an", "in", "on", "at", "to", "for",
            "of", "with", "and", "or", "but", "not", "do", "can", "their",
            "they", "them", "my", "me", "about", "tell", "know", "work",
            "live", "like", "from", "has", "have", "had",
        }

        keywords = [
            word.lower().strip("?.,!\"'")
            for word in question.split()
            if word.lower().strip("?.,!\"'") not in stop_words and len(word) > 2
        ]

        if not keywords:
            return ""

        # Scan log for matching messages
        matches: list[dict[str, Any]] = []
        with open(config.RAW_LOG_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    text = record.get("text", "").lower()
                    sender = record.get("sender", "").lower()

                    # Check if any keyword matches in text or sender name
                    if any(kw in text or kw in sender for kw in keywords):
                        matches.append(record)
                except json.JSONDecodeError:
                    continue

        if not matches:
            return ""

        # Format matches, most recent first
        matches.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
        formatted = []
        for msg in matches[:max_results]:
            sender = msg.get("sender", "Unknown")
            ts = msg.get("timestamp", "")[:10]  # Date only
            chat = msg.get("chat_name", "")
            text = msg.get("text", "")
            is_self = msg.get("is_self", False)
            who = "You" if is_self else sender
            formatted.append(f"[{ts}] ({chat}) **{who}**: {text}")

        return "\n".join(formatted)

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama's generate endpoint."""
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    f"{self._ollama_url}/api/generate",
                    json={
                        "model": self._model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 512,
                        },
                    },
                )
                resp.raise_for_status()
                return resp.json().get("response", "No response from LLM")
        except httpx.ConnectError:
            return (
                "❌ Cannot connect to Ollama. Make sure it's running: "
                "`ollama serve`"
            )
        except Exception as e:
            return f"❌ LLM query failed: {e}"

    def list_contacts(self) -> list[dict[str, Any]]:
        """List all known contacts with their fact count."""
        result = []
        for profile in self._extractor.get_all_profiles().values():
            result.append({
                "name": profile.display_name,
                "facts": len(profile.facts),
                "messages": profile.message_count,
                "last_updated": profile.last_updated,
            })
        result.sort(key=lambda x: x["messages"], reverse=True)
        return result
