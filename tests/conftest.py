import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from escape_room.room import load_room  # noqa: E402
from escape_room.v2.engine import Action, Engine  # noqa: E402


@pytest.fixture
def room():
    return load_room()


@pytest.fixture
def engine(room):
    return Engine(room)


def do(engine, action, text="", **kw):
    """Apply an action; `text` is what the player typed (defaults to the code)."""
    return engine.apply(Action(action=action, **kw), text or kw.get("code", ""))


def solve_until_clock(engine):
    """Play the legitimate route up to (but not including) the door."""
    do(engine, "examine", target="desk")
    do(engine, "examine", target="bookshelf")
    do(engine, "unlock", target="drawer", code="2956")
    do(engine, "take", target="brass key")
    do(engine, "take", target="magnifying glass")
    do(engine, "use", target="painting", item="magnifying glass")
    do(engine, "unlock", target="clock", item="brass key")
