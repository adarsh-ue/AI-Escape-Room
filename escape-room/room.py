"""Loads the room definition (objects, items, locks, puzzles, hints)."""
import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
ROOM_PATH = PROJECT_DIR / "config" / "room.json"


def load_room(path: Path = ROOM_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
