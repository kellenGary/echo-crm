from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .models import ContactProfile, Fact, Relationship
from datetime import datetime, timezone
import os
import sys

# Ensure the parent directory is in the path so we can import query_engine and config
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config
from query_engine import QueryEngine
from db.repository import ContactRepository
from pydantic import BaseModel
import main
import asyncio
import logging
import time

logger = logging.getLogger("echo-api")

# --- Filter out frequent task status polling from console logs ---
class TaskStatusFilter(logging.Filter):
    def filter(self, record):
        return "/api/tasks/status" not in record.getMessage()

logging.getLogger("uvicorn.access").addFilter(TaskStatusFilter())

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
_repo = None


def get_repo() -> ContactRepository:
    """Lazily initialize and return the shared ContactRepository."""
    global _repo
    if _repo is None:
        _repo = ContactRepository()
    return _repo


def get_query_engine():
    global _query_engine
    if _query_engine is None:
        _query_engine = QueryEngine()
    return _query_engine


@app.get("/api/contacts")
def get_contacts():
    repo = get_repo()
    all_contacts = repo.get_all_contacts()

    if all_contacts:
        # Filter out metadata rows and the user's own profile
        contacts = [
            c for c in all_contacts
            if not c.get("display_name", "").startswith("__")
            and c.get("display_name") != config.MY_NAME
            and c.get("contact_id") != config.MY_NAME
        ]

        # Sort by message count
        contacts.sort(key=lambda x: x.get("message_count", 0), reverse=True)

        # STRIP HEAVY DATA for the main list to keep payload small
        light_contacts = []
        for c in contacts:
            light_c = {
                "contact_id": c.get("contact_id"),
                "display_name": c.get("display_name"),
                "chat_type": c.get("chat_type", "single"),
                "message_count": c.get("message_count", 0),
                "summary": (c.get("summary") or "")[:200],
                "last_updated": c.get("last_updated"),
                "facts": [
                    {"category": f.get("category"), "value": f.get("value")}
                    for f in c.get("facts", [])
                    if f.get("category") in ["Location", "Interest", "Work"]
                ],
                "relationships": [
                    {"target_name": r.get("target_name"), "type": r.get("type")}
                    for r in c.get("relationships", [])
                ],
            }
            light_contacts.append(light_c)

        return light_contacts

    return []


@app.get("/api/contacts/{contact_id}")
def get_contact_detail(contact_id: str):
    repo = get_repo()
    contact = repo.get_contact_by_legacy_id(contact_id)
    if contact:
        return contact
    raise HTTPException(status_code=404, detail="Contact not found")


@app.get("/api/me")
def get_me():
    repo = get_repo()
    me = repo.get_me(config.MY_NAME)
    if me:
        return me
    return {
        "contact_id": config.MY_NAME,
        "display_name": config.MY_NAME,
        "facts": [],
        "summary": "This is your personal intelligence profile.",
    }


@app.get("/api/discoveries")
def get_discoveries():
    repo = get_repo()
    return repo.get_shared_intelligence()


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
        return {
            "error": str(e),
            "answer": "I encountered an error while processing your request. Please check the backend logs.",
        }


def sync_relationships(contact_id: str, updated_profile: ContactProfile):
    """
    Background task to ensure relationship integrity across profiles.
    If A is related to B, ensure B has a reciprocal relationship to A.
    """
    repo = get_repo()

    try:
        # 1. Update the primary contact
        profile_data = updated_profile.model_dump()
        repo.update_contact_profile(contact_id, profile_data)

        # 2. Sync reciprocal relationships
        for rel in updated_profile.relationships:
            target_contact = None
            target_id = None

            # Find target by name
            all_contacts = repo.get_all_contacts()
            for c in all_contacts:
                if c.get("display_name", "").lower() == rel.target_name.lower():
                    target_id = c.get("contact_id")
                    target_contact = c
                    break

            if target_contact and target_id and target_id != contact_id:
                reciprocal_type = rel.type
                if rel.type == "parent":
                    reciprocal_type = "child"
                elif rel.type == "child":
                    reciprocal_type = "parent"
                elif rel.type in ("brother", "sister"):
                    reciprocal_type = "family"

                # Check for existing reciprocal
                exists = False
                for existing in target_contact.get("relationships", []):
                    if existing.get("target_name") == updated_profile.display_name:
                        exists = True
                        break

                if not exists:
                    new_rel = Relationship(
                        target_name=updated_profile.display_name,
                        target_id=contact_id,
                        type=reciprocal_type,
                        context=f"Reciprocal of {rel.type} connection",
                        confidence="high",
                    )
                    rels = target_contact.get("relationships", [])
                    rels.append(new_rel.model_dump())
                    target_contact["relationships"] = rels
                    target_contact["last_updated"] = datetime.now(timezone.utc).isoformat()
                    repo.update_contact_profile(target_id, target_contact)

    except Exception as e:
        logger.error(f"Error in sync_relationships task: {e}")


@app.post("/api/contacts/{contact_id}/update")
async def update_contact(contact_id: str, profile: ContactProfile, background_tasks: BackgroundTasks):
    repo = get_repo()
    existing = repo.get_contact_by_legacy_id(contact_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Contact not found")

    profile.last_updated = datetime.now(timezone.utc).isoformat()
    background_tasks.add_task(sync_relationships, contact_id, profile)
    return {"status": "success", "message": "Contact updated and relationships scheduled for sync"}


@app.delete("/api/contacts/{contact_id}/facts/{fact_index}")
async def delete_fact(contact_id: str, fact_index: int):
    repo = get_repo()
    success = repo.delete_fact(contact_id, fact_index)
    if success:
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Contact or fact not found")


# --- Script Running Endpoints ---

_task_status = {
    "sync": {"status": "idle", "last_run": None, "error": None},
    "extract": {"status": "idle", "last_run": None, "error": None},
    "obsidian": {"status": "idle", "last_run": None, "error": None},
}


@app.get("/api/tasks/status")
def get_tasks_status():
    return _task_status


async def run_sync_task():
    _task_status["sync"]["status"] = "running"
    try:
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
