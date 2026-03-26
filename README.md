# 🌊 Echo CRM

A personal CRM powered by your chat history. Echo CRM syncs messages from **Beeper**, extracts contact profiles using **Google Gemini**, and provides a unified workspace to explore your personal relationships and knowledge.

---

## ✨ Features

- **Multi-Network Sync**: Connect to Beeper to ingest messages from iMessage, WhatsApp, Telegram, Signal, and more.
- **AI-Powered Extraction**: Automatically identifies contacts, extracts facts, and maps relationships using Google's Gemini 3.1 Flash.
- **Semantic Search**: Search through your message history using natural language (powered by ChromaDB and Gemini Embeddings).
- **Relational Intelligence**: Maps your social graph and tracks how people are connected to each other.
- **Obsidian Integration**: Generates an interlinked "Beeper Intelligence" vault in Obsidian for visual knowledge graph exploration.
- **Interactive Web UI**: A modern Next.js dashboard with a force-directed relationship graph and detailed contact workspaces.
- **Note-to-Self Bot**: Query your CRM directly within Beeper by messaging your "Note to Self" chat.

---

## 🛠️ Tech Stack

- **Backend**: Python (FastAPI, asyncio)
- **Frontend**: Next.js, React, Tailwind CSS, D3.js
- **Database**: 
  - **PostgreSQL** with `pgvector` (Structured facts, contacts, and relationships)
  - **ChromaDB** (Message semantic search)
- **LLM**: Google Gemini 3.1 Flash (Extraction, Search, and Bot Chat)
- **Ingestion**: Beeper Desktop API

---

## 🚀 Getting Started

### 1. Prerequisites

- **PostgreSQL**: Installed and running (v15+ recommended).
- **pgvector Extension**: Must be installed in your PostgreSQL instance.
- **Beeper Desktop**: Must be running and logged in, with the **Desktop API** enabled in settings.
- **Google Gemini API Key**: Obtain from [Google AI Studio](https://aistudio.google.com/).
- **Node.js & npm**: For the web dashboard.
- **Python 3.10+**: For the core system and API.

### 2. Database Setup

Create a new database and run the initialization script:
```bash
# Create database
createdb echo_crm

# Run schema initialization
psql -d echo_crm -f db/init_schema.sql
```

### 3. Environment Configuration

Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your_gemini_api_key
BEEPER_API_TOKEN=your_beeper_desktop_api_token
DATABASE_URL=postgresql://localhost:5432/echo_crm
```

### 4. Core System Installation

```bash
# Set up virtual environment
python -m venv .venv
source .venv/bin/activate  # Mac/Linux

# Install dependencies (ensure pip is updated)
pip install -r requirements.txt
```
*(Note: If `requirements.txt` is missing in root, ensure you install `google-genai`, `chromadb`, `psycopg2-binary`, `python-dotenv`, `fastapi`, `uvicorn`)*

### 5. Web Dashboard Installation

```bash
cd echo-web
npm install

# Setup web-specific python environment (used by the Next.js API)
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 📖 Usage

### Core CLI Commands

Echo CRM is primarily managed via `main.py`:

```bash
# Sync new messages from Beeper to local logs
python main.py sync

# Index message history for semantic search
python main.py index

# Run AI extraction to build/update contact profiles
python main.py extract

# Full pipeline: sync → index → extract → ask
python main.py run

# Start the 'Note to Self' bot listener
python main.py bot

# Generate Obsidian notes
python main.py obsidian
```

### Running the Web Dashboard

From the `echo-web` folder:
```bash
npm run dev
```
The dashboard will be available at `http://localhost:3000`. This command concurrently starts the Next.js frontend and the FastAPI backend.

---

## 🧠 System Architecture

1. **Ingestion**: `beeper_client.py` fetches messages via local HTTP requests to Beeper Desktop.
2. **Persistence**: Messages are logged to `data/messages.jsonl` and indexed into **ChromaDB**.
3. **Intelligence**: `profile_extractor.py` sends message batches to **Gemini 3.1 Flash** to identify entities and facts.
4. **Relational Data**: Extracted contacts and facts are stored in **PostgreSQL**.
5. **Consumption**: The **Next.js** frontend or the **Beeper Bot** queries the DB and Vector Store to answer user questions.

---

## 📝 License & Attribution

Designed and maintained by **Kellen Gary**. 
Built for personal relationship management and social intelligence.
