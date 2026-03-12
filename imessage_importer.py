import sqlite3
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import re

DB_PATH = Path("data/chat.db")
LOG_PATH = Path("data/messages.jsonl")
APPLE_EPOCH = 978307200

# To try and deduplicate messages we already fetched from beeper API
def normalize_text(text):
    if not text: return ""
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

def migrate():
    print(f"Opening database {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT ROWID, id FROM handle")
    handles = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.execute("SELECT ROWID, chat_identifier, display_name FROM chat")
    chats_by_id = {}
    for row in cursor.fetchall():
        chat_id = "imsg_chat_" + str(row[0])
        display_name = row[2] if row[2] else row[1]
        identifier = row[1]
        chat_type = "single"
        if identifier and ("chat" in identifier or ";" in identifier):
            chat_type = "group"
        chats_by_id[row[0]] = {
            "chat_id": chat_id,
            "chat_name": display_name,
            "chat_type": chat_type
        }

    cursor.execute("SELECT chat_id, message_id FROM chat_message_join")
    chat_joins = {}
    for chat_id, msg_id in cursor.fetchall():
        chat_joins[msg_id] = chat_id

    query = """
        SELECT ROWID, text, handle_id, date, is_from_me, cache_roomnames
        FROM message
        WHERE text IS NOT NULL AND text != ''
        ORDER BY date ASC
    """
    cursor.execute(query)
    
    records = []
    
    for row in cursor.fetchall():
        msg_id = "apple_db_" + str(row[0])
        text = row[1]
        handle_id = row[2] or 0
        date_val = row[3]
        is_self = bool(row[4])
        
        if date_val > 10000000000:
            unix_ts = (date_val / 1000000000) + APPLE_EPOCH
        else:
            unix_ts = date_val + APPLE_EPOCH
            
        try:
            timestamp = datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()
        except:
            timestamp = datetime.now(timezone.utc).isoformat()

        sender = "You" if is_self else handles.get(handle_id, "Unknown")
        
        chat_id_num = chat_joins.get(row[0])
        chat_info = chats_by_id.get(chat_id_num, {"chat_id": f"unknown_{handle_id}", "chat_name": sender, "chat_type": "single"})
        
        import mac_contacts
        resolved_sender = mac_contacts.resolve_contact(sender, sender)

        chat_name = chat_info["chat_name"]
        resolved_chat_name = mac_contacts.resolve_contact(chat_name, chat_name)
        if resolved_chat_name == "Unknown" and str(handle_id) != "0":
             resolved_chat_name = resolved_sender
        
        record = {
            "chat_id": chat_info["chat_id"],
            "chat_name": resolved_chat_name,
            "chat_type": chat_info["chat_type"],
            "message_id": msg_id,
            "sender_name": resolved_sender,
            "sender_id": sender,
            "is_self": is_self,
            "timestamp": timestamp,
            "text": text,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        records.append(record)
    
    # Existing read
    existing_messages = set()
    existing_text_norm = set()
    if LOG_PATH.exists():
        with open(LOG_PATH) as f:
            for line in f:
                if not line.strip(): continue
                try:
                    obj = json.loads(line)
                    if "message_id" in obj:
                        existing_messages.add(obj["message_id"])
                        norm_text = normalize_text(obj.get("text", ""))
                        if norm_text:
                            existing_text_norm.add(norm_text)
                except: pass
                
    new_records = []
    for r in records:
        if r["message_id"] in existing_messages:
            continue
        # Also skip if it seems like a duplicate of a message fetched via Beeper API 
        # (Be slightly strict about this to avoid massive duplication in the AI inputs)
        norm_r_text = normalize_text(r["text"])
        if len(norm_r_text) > 15 and norm_r_text in existing_text_norm:
            continue
            
        new_records.append(r)
        
    print(f"Total messages in Apple DB: {len(records)}")
    print(f"Adding {len(new_records)} entirely new historical messages to the Beeper JSONL log.")
    
    with open(LOG_PATH, "a") as f:
        for r in new_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    migrate()
