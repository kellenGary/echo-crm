"""
Vector Store — Handles semantic search using Ollama embeddings and ChromaDB.
"""

import logging
import json
from typing import Any, List, Optional
import httpx
import chromadb
from chromadb.config import Settings
import config

logger = logging.getLogger(__name__)

class OllamaEmbeddingFunction:
    """Custom embedding function that calls Ollama's API."""
    
    def __init__(self, model_name: str, base_url: str):
        self.model_name = model_name
        self.base_url = base_url

    def __call__(self, input: List[str]) -> List[List[float]]:
        embeddings = []
        try:
            with httpx.Client(timeout=60.0) as client:
                for text in input:
                    resp = client.post(
                        f"{self.base_url}/api/embeddings",
                        json={"model": self.model_name, "prompt": text},
                    )
                    resp.raise_for_status()
                    embeddings.append(resp.json()["embedding"])
            return embeddings
        except Exception as e:
            logger.error(f"Failed to get embeddings from Ollama: {e}")
            return [[0.0] * 768 for _ in input]

    def name(self) -> str:
        return "ollama"

class VectorStore:
    """
    Manages indexing and searching of messages using vector embeddings.
    """

    def __init__(self):
        self._client = chromadb.PersistentClient(
            path=str(config.VECTOR_DB_DIR),
            settings=Settings(allow_reset=True)
        )
        
        self._embed_fn = OllamaEmbeddingFunction(
            model_name=config.OLLAMA_EMBED_MODEL,
            base_url=config.OLLAMA_BASE_URL
        )
        
        # Simple collection for all messages
        self._collection = self._client.get_or_create_collection(
            name="messages",
            embedding_function=self._embed_fn,
            metadata={"hnsw:space": "cosine"}
        )

    def index_messages(self, messages: List[dict]):
        """
        Add messages to the vector index.
        Each message should have: id, text, sender, timestamp, chat_name.
        """
        if not messages:
            return

        ids = []
        documents = []
        metadatas = []

        for msg in messages:
            text = msg.get("text", "").strip()
            if not text or len(text) < 5:  # Skip tiny/empty messages
                continue
                
            # Create a descriptive document string for better semantic matching
            # Format: [Date] Sender in Chat: Message
            sender = msg.get("sender", "Unknown")
            chat = msg.get("chat_name", "Unknown Chat")
            ts = msg.get("timestamp", "")[:10]
            
            doc_content = f"[{ts}] {sender} in {chat}: {text}"
            
            ids.append(msg["id"])
            documents.append(doc_content)
            metadatas.append({
                "sender": sender,
                "chat_name": chat,
                "timestamp": msg.get("timestamp", ""),
                "is_self": bool(msg.get("is_self", False))
            })

        if ids:
            # upsert handles both new and existing IDs
            self._collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            logger.info(f"Indexed {len(ids)} messages into vector store.")

    def search(self, query: str, limit: int = 20) -> List[dict]:
        """
        Perform semantic search for phrases or questions.
        Returns a list of message objects.
        """
        results = self._collection.query(
            query_texts=[query],
            n_results=limit
        )

        formatted = []
        if not results or not results["ids"]:
            return []

        # ChromaDB returns nested lists
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            formatted.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i], # This contains the formatted doc
                "sender": meta["sender"],
                "chat_name": meta["chat_name"],
                "timestamp": meta["timestamp"],
                "is_self": meta["is_self"],
                "distance": results["distances"][0][i] if "distances" in results else 0
            })
            
        return formatted

    def get_indexed_count(self) -> int:
        """Returns number of messages in the index."""
        return self._collection.count()
