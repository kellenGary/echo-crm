"""
Central configuration for the Beeper message logging and contact intelligence service.
"""

import os
from pathlib import Path
import os

MY_NAME = "Kellen"

# --- Beeper Desktop API ---
BEEPER_BASE_URL = os.getenv("BEEPER_BASE_URL", "http://localhost:23373")
BEEPER_API_TOKEN = os.getenv("BEEPER_API_TOKEN", "7160b021-e5a0-4c29-8c3f-816f31f99151")

# --- Ollama LLM ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# --- Extraction Performance ---
EXTRACTION_BATCH_SIZE = int(os.getenv("EXTRACTION_BATCH_SIZE", "50"))
EXTRACTION_CONCURRENCY = int(os.getenv("EXTRACTION_CONCURRENCY", "4"))

# --- Data Storage ---
DATA_DIR = Path(os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data")))
RAW_LOG_FILE = DATA_DIR / "messages.jsonl"          # Raw message log (JSON Lines)
CONTACTS_FILE = DATA_DIR / "contacts.json"           # Extracted contact profiles
SYNC_STATE_FILE = DATA_DIR / "sync_state.json"       # Tracks last sync position per chat
VECTOR_STATE_FILE = DATA_DIR / "vector_state.json"   # Tracks last indexed line
VECTOR_DB_DIR = DATA_DIR / "vector_db"               # ChromaDB storage

# --- Note to Self Chatbot ---
NOTE_TO_SELF_CHAT_ID = os.getenv(
    "NOTE_TO_SELF_CHAT_ID", "!YvvsvIjGYzPZdlDEua:beeper.com"
)
BOT_POLL_INTERVAL = int(os.getenv("BOT_POLL_INTERVAL", "3"))  # seconds

# --- Sync Settings ---
SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL", "300"))  # 5 minutes
MAX_MESSAGES_PER_CHAT = int(os.getenv("MAX_MESSAGES_PER_CHAT", "200"))  # Per sync cycle
INCLUDE_GROUP_CHATS = os.getenv("INCLUDE_GROUP_CHATS", "true").lower() == "true"

# --- Obsidian Integration ---
OBSIDIAN_VAULT_PATH = Path(
    os.getenv("OBSIDIAN_VAULT", os.path.expanduser("~/Documents/Obsidian Vault"))
)
OBSIDIAN_BEEPER_DIR = OBSIDIAN_VAULT_PATH / "Beeper Intelligence"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)
