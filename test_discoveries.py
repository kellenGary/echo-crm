import sys
from pathlib import Path
sys.path.append(str(Path.cwd()))
from storage import DataStore
import config
import json

ds = DataStore(config.DATA_DIR / "echo_nosql.json")
discoveries = ds.get_shared_intelligence()
print(f"Found {len(discoveries)} discoveries")
print(json.dumps(discoveries[:2], indent=2))
