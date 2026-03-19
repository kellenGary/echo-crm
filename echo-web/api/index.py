from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .models import ContactProfile, Fact, Relationship
from datetime import datetime, timezone
import json
import os
import sys
# Ensure the parent directory is in the path so we can import query_engine and config
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config
from query_engine import QueryEngine
from pydantic import BaseModel
import main
import asyncio
import logging

logger = logging.getLogger("echo-api")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str

_query_engine = None

def get_query_engine():
    global _query_engine
    if _query_engine is None:
        _query_engine = QueryEngine()
    return _query_engine

# This would typically read from your data/chat.db or JSON files
# For now, let's provide some mock data that mirrors your Python logic

@app.get("/api/contacts")
def get_contacts():
    # Path to the real contacts data
    data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/contacts.json"))
    print(f"DEBUG: Checking for contacts at {data_path}")
    
    if os.path.exists(data_path):
        try:
            with open(data_path, "r") as f:
                db = json.load(f)
                contacts_dict = db.get("contacts", {})
                if contacts_dict:
                    # Convert dict to list
                    contacts = list(contacts_dict.values())
                    
                    # Filter out the 'Me' profile (the user)
                    contacts = [c for c in contacts if c.get("display_name") != config.MY_NAME and c.get("contact_id") != config.MY_NAME]
                    
                    # Sort by message count
                    contacts.sort(key=lambda x: x.get("message_count", 0), reverse=True)
                    return contacts
        except Exception as e:
            print(f"Error reading contacts file: {e}")

    # Fallback to mock data if real data is empty or file missing
    contacts = [
        {
            "contact_id": "mock:1",
            "display_name": "Alex Thompson (Mock)",
            "facts": [
                {"category": "Work", "value": "Senior Engineering Manager at TechCorp", "confidence": "high"},
                {"category": "Preference", "value": "Prefers async communication", "confidence": "medium"}
            ],
            "last_updated": datetime.now().isoformat(),
            "message_count": 154
        },
        {
            "contact_id": "mock:2",
            "display_name": "Sarah Chen (Mock)",
            "facts": [
                {"category": "Location", "value": "San Francisco, CA", "confidence": "high"},
                {"category": "Interest", "value": "Aviation and kite surfing", "confidence": "high"}
            ],
            "last_updated": datetime.now().isoformat(),
            "message_count": 82
        }
    ]
    return contacts

@app.get("/api/contacts/{contact_id}")
def get_contact_detail(contact_id: str):
    data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/contacts.json"))
    if os.path.exists(data_path):
        try:
            with open(data_path, "r") as f:
                db = json.load(f)
                contacts_dict = db.get("contacts", {})
                if contact_id in contacts_dict:
                    return contacts_dict[contact_id]
        except Exception as e:
            print(f"Error reading contact {contact_id}: {e}")
            raise HTTPException(status_code=500, detail="Internal Server Error")
    
    raise HTTPException(status_code=404, detail="Contact not found")

@app.get("/api/me")
def get_me():
    data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/contacts.json"))
    if os.path.exists(data_path):
        try:
            with open(data_path, "r") as f:
                db = json.load(f)
                contacts_dict = db.get("contacts", {})
                # Look for the profile that matches MY_NAME
                for cid, profile in contacts_dict.items():
                    if profile.get("display_name") == config.MY_NAME or cid == config.MY_NAME:
                        return profile
        except Exception as e:
            print(f"Error reading me profile: {e}")
    
    return {
        "contact_id": config.MY_NAME,
        "display_name": config.MY_NAME,
        "facts": [],
        "summary": "This is your personal intelligence profile."
    }

@app.get("/api/discoveries")
def get_discoveries():
    data_path = os.path.join(os.path.dirname(__file__), "../../data/contacts.json")
    if os.path.exists(data_path):
        try:
            with open(data_path, "r") as f:
                db = json.load(f)
                return db.get("discoveries", [])
        except Exception as e:
            print(f"Error reading discoveries: {e}")
    return []

@app.get("/api/health")
def health_check():
    return {"status": "ok", "backend": "python/fastapi"}

@app.post("/api/ask")
def ask_question(request: AskRequest):
    try:
        engine = get_query_engine()
        answer = engine.ask(request.question)
        return {"answer": answer}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "answer": "I encountered an error while processing your request. Please check the backend logs."}

def sync_relationships(contact_id: str, updated_profile: ContactProfile):
    """
    Background task to ensure relationship integrity across profiles.
    If A is related to B, ensure B has a reciprocal relationship to A.
    """
    data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/contacts.json"))
    if not os.path.exists(data_path):
        return

    try:
        with open(data_path, "r") as f:
            db = json.load(f)
            contacts = db.get("contacts", {})
        
        # 1. Update the primary contact
        contacts[contact_id] = updated_profile.model_dump()
        
        # 2. Sync reciprocal relationships
        for rel in updated_profile.relationships:
            target_profile = None
            target_id = None
            
            # Find target by ID or Name
            if rel.target_id and rel.target_id in contacts:
                target_id = rel.target_id
            else:
                for cid, p in contacts.items():
                    if p["display_name"].lower() == rel.target_name.lower():
                        target_id = cid
                        break
            
            if target_id and target_id != contact_id:
                target_data = contacts[target_id]
                reciprocal_type = rel.type # Default to same type (e.g. colleague)
                
                # Simple reciprocal logic
                if rel.type == "parent": reciprocal_type = "child"
                elif rel.type == "child": reciprocal_type = "parent"
                elif rel.type == "brother" or rel.type == "sister": reciprocal_type = "family"
                
                # Check for existing
                exists = False
                for existing in target_data.get("relationships", []):
                    if existing["target_name"] == updated_profile.display_name:
                        exists = True
                        break
                
                if not exists:
                    new_rel = Relationship(
                        target_name=updated_profile.display_name,
                        target_id=contact_id,
                        type=reciprocal_type,
                        context=f"Reciprocal of {rel.type} connection",
                        confidence="high"
                    )
                    if "relationships" not in target_data:
                        target_data["relationships"] = []
                    target_data["relationships"].append(new_rel.model_dump())

        # Save back
        db["contacts"] = contacts
        with open(data_path, "w") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
            
    except Exception as e:
        print(f"Error in sync_relationships task: {e}")

@app.post("/api/contacts/{contact_id}/update")
async def update_contact(contact_id: str, profile: ContactProfile, background_tasks: BackgroundTasks):
    data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/contacts.json"))
    
    if not os.path.exists(data_path):
        raise HTTPException(status_code=404, detail="Contacts database not found")
        
    # Update local memory if needed or just trigger persistence
    profile.last_updated = datetime.now(timezone.utc).isoformat()
    
    # Schedule relationship sync and persistence
    background_tasks.add_task(sync_relationships, contact_id, profile)
    
    return {"status": "success", "message": "Contact updated and relationships scheduled for sync"}

@app.delete("/api/contacts/{contact_id}/facts/{fact_index}")
async def delete_fact(contact_id: str, fact_index: int):
    data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/contacts.json"))
    
    try:
        with open(data_path, "r") as f:
            db = json.load(f)
            contacts = db.get("contacts", {})
        
        if contact_id not in contacts:
            raise HTTPException(status_code=404, detail="Contact not found")
            
        profile_data = contacts[contact_id]
        if 0 <= fact_index < len(profile_data.get("facts", [])):
            profile_data["facts"].pop(fact_index)
            profile_data["last_updated"] = datetime.now(timezone.utc).isoformat()
            
            with open(data_path, "w") as f:
                json.dump(db, f, indent=2, ensure_ascii=False)
            return {"status": "success"}
        else:
            raise HTTPException(status_code=400, detail="Invalid fact index")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Script Running Endpoints ---

_task_status = {
    "sync": {"status": "idle", "last_run": None, "error": None},
    "extract": {"status": "idle", "last_run": None, "error": None},
    "obsidian": {"status": "idle", "last_run": None, "error": None}
}

@app.get("/api/tasks/status")
def get_tasks_status():
    return _task_status

async def run_sync_task():
    _task_status["sync"]["status"] = "running"
    try:
        # main.cmd_sync is synchronous
        result = main.cmd_sync()
        if result == 0:
            _task_status["sync"]["status"] = "success"
        else:
            _task_status["sync"]["status"] = "error"
            _task_status["sync"]["error"] = f"Exit code {result}"
    except Exception as e:
        _task_status["sync"]["status"] = "error"
        _task_status["sync"]["error"] = str(e)
    _task_status["sync"]["last_run"] = datetime.now().isoformat()

async def run_extract_task():
    _task_status["extract"]["status"] = "running"
    try:
        # main.cmd_extract is asynchronous
        result = await main.cmd_extract()
        if result == 0:
            _task_status["extract"]["status"] = "success"
        else:
            _task_status["extract"]["status"] = "error"
            _task_status["extract"]["error"] = f"Exit code {result}"
    except Exception as e:
        _task_status["extract"]["status"] = "error"
        _task_status["extract"]["error"] = str(e)
    _task_status["extract"]["last_run"] = datetime.now().isoformat()

async def run_obsidian_task():
    _task_status["obsidian"]["status"] = "running"
    try:
        # main.cmd_obsidian is synchronous
        main.cmd_obsidian()
        _task_status["obsidian"]["status"] = "success"
    except Exception as e:
        _task_status["obsidian"]["status"] = "error"
        _task_status["obsidian"]["error"] = str(e)
    _task_status["obsidian"]["last_run"] = datetime.now().isoformat()

@app.post("/api/run/sync")
async def trigger_sync(background_tasks: BackgroundTasks):
    if _task_status["sync"]["status"] == "running":
        return {"status": "already_running"}
    background_tasks.add_task(run_sync_task)
    return {"status": "started"}

@app.post("/api/run/extract")
async def trigger_extract(background_tasks: BackgroundTasks):
    if _task_status["extract"]["status"] == "running":
        return {"status": "already_running"}
    background_tasks.add_task(run_extract_task)
    return {"status": "started"}

@app.post("/api/run/obsidian")
async def trigger_obsidian(background_tasks: BackgroundTasks):
    if _task_status["obsidian"]["status"] == "running":
        return {"status": "already_running"}
    background_tasks.add_task(run_obsidian_task)
    return {"status": "started"}
