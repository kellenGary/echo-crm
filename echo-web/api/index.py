from fastapi import FastAPI
from .models import ContactProfile, Fact
from datetime import datetime
import json
import os

app = FastAPI()

# This would typically read from your data/chat.db or JSON files
# For now, let's provide some mock data that mirrors your Python logic

@app.get("/api/contacts")
def get_contacts():
    # In a real app, you would import your profile_extractor logic here
    # and query your local SQLite DB. 
    # Vercel Serverless has some limits on DB size, so usually you'd use a remote DB,
    # but for local pairing this works perfectly.
    
    contacts = [
        {
            "contact_id": "1",
            "display_name": "Alex Thompson",
            "facts": [
                {"category": "Work", "value": "Senior Engineering Manager at TechCorp", "confidence": "high"},
                {"category": "Preference", "value": "Prefers async communication", "confidence": "medium"}
            ],
            "last_updated": datetime.now().isoformat(),
            "message_count": 154
        },
        {
            "contact_id": "2",
            "display_name": "Sarah Chen",
            "facts": [
                {"category": "Location", "value": "San Francisco, CA", "confidence": "high"},
                {"category": "Interest", "value": "Aviation and kite surfing", "confidence": "high"}
            ],
            "last_updated": datetime.now().isoformat(),
            "message_count": 82
        }
    ]
    return contacts

@app.get("/api/health")
def health_check():
    return {"status": "ok", "backend": "python/fastapi"}
