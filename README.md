# Echo CRM

A personal CRM powered by your chat history. Echo CRM syncs messages from Beeper, extracts contact profiles using a local LLM, and lets you query for personal details about your contacts.

## Usage

```bash
# Sync messages from Beeper to local log
python main.py sync

# Run LLM extraction on new messages
python main.py extract

# Interactive Q&A about your contacts
python main.py ask

# List all known contacts
python main.py contacts

# Full pipeline: sync → extract → ask
python main.py run

# Run sync + extract on a loop (background)
python main.py daemon

# Start the Note to self chatbot
python main.py bot

# Generate interlinked Obsidian notes
python main.py obsidian
```
