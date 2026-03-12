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
from vector_store import VectorStore

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
        self._vector_store = VectorStore()

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
        
        if profile.summary:
            lines.append(f"Summary: {profile.summary}")

        if profile.facts:
            lines.append("Facts:")
            for fact in profile.facts:
                line = f"- **{fact.category}**: {fact.value}"
                if fact.source_quote:
                    line += f' (Source: "{fact.source_quote}")'
                lines.append(line)
        
        return "\n".join(lines)

    def _search_raw_messages(self, question: str, max_results: int = 25) -> str:
        """Search the vector store for messages relevant to the question."""
        matches = self._vector_store.search(question, limit=max_results)
        
        if not matches:
            return ""

        formatted = []
        for msg in matches:
            # The 'text' in search results is already formatted by VectorStore
            formatted.append(msg["text"])

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
