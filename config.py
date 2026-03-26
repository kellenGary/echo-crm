"""
Central configuration for the Beeper message logging and contact intelligence service.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # Load .env file before reading env vars

MY_NAME = "Kellen Gary"

# --- Beeper Desktop API ---
BEEPER_BASE_URL = os.getenv("BEEPER_BASE_URL", "http://localhost:23373")
BEEPER_API_TOKEN = os.getenv("BEEPER_API_TOKEN")

# --- Google Gemini API ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "text-embedding-004")

# --- Gemini Rate Limits (Gemini 3 Flash Testing) ---
GEMINI_RPM = float(os.getenv("GEMINI_RPM", "4000.0"))
GEMINI_RPD = int(os.getenv("GEMINI_RPD", "4000000"))
GEMINI_CONTEXT_WINDOW = 250000

# --- Extraction Performance ---
EXTRACTION_BATCH_SIZE = int(os.getenv("EXTRACTION_BATCH_SIZE", "100"))
EXTRACTION_CONCURRENCY = int(os.getenv("EXTRACTION_CONCURRENCY", "100"))

# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Data Storage ---
DATA_DIR = Path(os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data")))
GEMINI_MAX_SPEND = float(os.getenv("GEMINI_MAX_SPEND", "25.0"))
GEMINI_USAGE_FILE = DATA_DIR / "gemini_usage.json"
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
