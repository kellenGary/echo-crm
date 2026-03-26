import os
import shutil
import json
import logging
from pathlib import Path
import config
from db import Base, get_engine, init_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("reset-system")

def wipe_files():
    """Wipe all data files and vector database."""
    logger.info("Wiping local data files...")
    
    files_to_delete = [
        config.RAW_LOG_FILE,
        config.CONTACTS_FILE,
        config.SYNC_STATE_FILE,
        config.VECTOR_STATE_FILE,
        config.GEMINI_USAGE_FILE,
        config.DATA_DIR / "echo_nosql.json",
        config.DATA_DIR / "phone_book.json",
        config.DATA_DIR / "chat.db"
    ]
    
    for f in files_to_delete:
        if f.exists():
            logger.info(f"  Deleting {f.name}...")
            f.unlink()
            
    if config.VECTOR_DB_DIR.exists():
        logger.info("  Deleting Vector DB directory...")
        shutil.rmtree(config.VECTOR_DB_DIR)

def wipe_database():
    """Drop and recreate all PostgreSQL tables."""
    logger.info("Wiping PostgreSQL database...")
    try:
        engine = get_engine()
        # Ensure models are imported so metadata knows about them
        from db import models 
        
        logger.info("  Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
        
        logger.info("  Recreating schema...")
        init_db()
        logger.info("  Database reset successful.")
    except Exception as e:
        logger.error(f"  Failed to reset database: {e}")
        logger.warning("  (Make sure PostgreSQL is running and the database 'echo_crm' exists)")

def wipe_obsidian():
    """Clear the Obsidian vault directory."""
    if config.OBSIDIAN_BEEPER_DIR.exists():
        logger.info(f"Wiping Obsidian notes in {config.OBSIDIAN_BEEPER_DIR}...")
        shutil.rmtree(config.OBSIDIAN_BEEPER_DIR)
        config.OBSIDIAN_BEEPER_DIR.mkdir(parents=True, exist_ok=True)

def main():
    print("\n⚠️  WARNING: This will delete ALL synced messages, extracted profiles, and database records.")
    confirm = input("Are you sure you want to proceed? (y/N): ").lower()
    
    if confirm == 'y':
        wipe_files()
        wipe_database()
        wipe_obsidian()
        logger.info("✨ System reset complete. You can now start with a fresh sync.")
    else:
        logger.info("Reset cancelled.")

if __name__ == "__main__":
    main()
