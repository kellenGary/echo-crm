"""
Vector Store — Handles semantic search using Gemini embeddings and ChromaDB.
"""

import logging
from typing import List

import chromadb
from chromadb.config import Settings
from chromadb import EmbeddingFunction, Documents, Embeddings

import config
from gemini_client import GeminiClient

logger = logging.getLogger(__name__)


class GeminiEmbeddingFunction(EmbeddingFunction):
    """Custom ChromaDB embedding function that calls Gemini's embedding API."""
    
    def __init__(self):
        self._gemini = GeminiClient()

    def __call__(self, input: List[str]) -> List[List[float]]:
        return self._gemini.embed(input)

    def embed_query(self, input: str) -> List[float]:
        """Embed a single query string."""
        return self.__call__([input])[0]

    def embed_documents(self, input: List[str]) -> List[List[float]]:
        """Embed a list of document strings."""
        return self.__call__(input)

    def name(self) -> str:
        return "gemini"


class VectorStore:
    """
    Manages indexing and searching of messages using vector embeddings.
    """

    def __init__(self):
        self._client = chromadb.PersistentClient(
            path=str(config.VECTOR_DB_DIR),
            settings=Settings(allow_reset=True)
        )
        
        self._embed_fn = GeminiEmbeddingFunction()
        
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
        # Explicitly embed the query
        query_embeddings = self._embed_fn([query])
        
        results = self._collection.query(
            query_embeddings=query_embeddings,
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
