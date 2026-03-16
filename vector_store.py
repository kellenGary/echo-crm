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
        from concurrent.futures import ThreadPoolExecutor
        
        def get_one(text: str) -> List[float]:
            try:
                # Use the newer /api/embed endpoint which is more robust
                with httpx.Client(timeout=60.0) as client:
                    resp = client.post(
                        f"{self.base_url}/api/embed",
                        json={"model": self.model_name, "input": text},
                    )
                    if resp.status_code != 200:
                        logger.error(f"Ollama embedding error ({resp.status_code}): {resp.text}")
                        resp.raise_for_status()
                    
                    data = resp.json()
                    # /api/embed returns {"embeddings": [[...]]}
                    if "embeddings" in data:
                        return data["embeddings"][0]
                    # Fallback to older /api/embeddings format if needed
                    elif "embedding" in data:
                        return data["embedding"]
                    else:
                        logger.error(f"Unexpected response format from Ollama: {data}")
                        return [0.0] * 768
            except Exception as e:
                logger.error(f"Failed to get embedding from Ollama model '{self.model_name}': {e}")
                return [0.0] * 768

        # Parallelize embedding calls
        with ThreadPoolExecutor(max_workers=10) as executor:
            embeddings = list(executor.map(get_one, input))
            
        return embeddings

    def embed_query(self, input: str) -> List[float]:
        """Embed a single query string (supporting 'input' keyword)."""
        return self.__call__([input])[0]

    def embed_documents(self, input: List[str]) -> List[List[float]]:
        """Embed a list of document strings (supporting 'input' keyword)."""
        return self.__call__(input)

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
