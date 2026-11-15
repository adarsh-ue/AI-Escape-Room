"""Version 2 game engine: Python owns the game state and decides every outcome.

The LLM never sees codes or solutions and cannot change the state. It only
(1) turns the player's words into an Action and (2) narrates the Result.
"""
import copy
import re
from dataclasses import asdict, dataclass, field

from pydantic import BaseModel, Field

ACTIONS = ["look", "examine", "take", "unlock", "use", "inventory", "hint", "other"]
ARTICLES = re.compile(r"^(?:the|a|an|my|that|this|your)\s+")


class Action(BaseModel):
    action: str = Field(description="One of: " + ", ".join(ACTIONS))
    target: str = Field(default="", description="Object or item the action is aimed at")
    item: str = Field(default="", description="Inventory item being used, if any")
    code: str = Field(default="", description="Digits the player typed, if any")


@dataclass
class Result:
    ok: bool                 # did the action succeed?
    event: str               # machine-readable outcome, e.g. "wrong_code"
    facts: str               # the only information the narrator may use
    escaped: bool = False
    progress: bool = False   # did the game state move forward?


def new_state() -> dict:
    """Everything the game remembers. JSON-serialisable."""
    return {
        "examined": [],          # objects looked at
        "unlocked": [],          # objects opened
        "visible_items": {},     # item -> where it lies (revealed, not yet taken)
        "inventory": [],         # items the player holds
        "solved": [],            # puzzle ids
        "door_open": False,
        "turns": 0,
        "turns_since_progress": 0,
        "failed_attempts": {},   # object -> wrong code/item count
        "log": [],               # one entry per turn
    }


class Engine:
    def __init__(self, room: dict, state: dict | None = None):
        self.room = room
        self.objects = room["objects"]
        self.items = room["items"]
        self.state = state if state is not None else new_state()
        self._names = {}
        for kind, table in (("object", self.objects), ("item", self.items)):
            for key, spec in table.items():
                for alias in [key] + spec.get("aliases", []):
                    self._names[alias.lower()] = (kind, key)

    # ------------------------------------------------------------------ names
    def resolve(self, name: str):
        """Map player wording to ("object"|"item", canonical_name), or None."""
        n = ARTICLES.sub("", (name or "").lower().strip(" .!?'\""))
        if not n:
            return None
        if n in self._names:
            return self._names[n]
        # longest known name contained as whole words, e.g. "old wooden desk" -> desk
        hits = [a for a in self._names if re.search(rf"\b{re.escape(a)}\b", n)]
        return self._names[max(hits, key=len)] if hits else None

    def known_items(self) -> list[str]:
        """Items the player has seen (visible or held) - safe to tell the LLM."""
        return list(self.state["inventory"]) + list(self.state["visible_items"])

    def public_view(self) -> dict:
        """Current status without any secrets - this is all the narrator sees."""
        s = self.state
        return {
            "objects": {
                o: ("open" if o in s["unlocked"] else "locked") if "lock" in spec else "-"
                for o, spec in self.objects.items()
            },
            "inventory": s["inventory"],
            "items_lying_around": list(s["visible_items"]),
            "puzzles_solved": len(s["solved"]),
            "door_open": s["door_open"],
        }

    # --------------------------------------------------------------- dispatch
    def apply(self, action: Action, player_text: str = "") -> Result:
        a = action.action if action.action in ACTIONS else "other"
        # A code only counts if the player actually typed those digits.
        code = re.sub(r"\D", "", action.code or "")
        if code and code not in re.sub(r"\D", "", player_text or code):
            code = ""
        handler = getattr(self, f"_{a}")
        result = handler(action.target, action.item, code) if a in ("examine", "take", "unlock", "use") else handler()

        s = self.state
        s["turns"] += 1
        s["turns_since_progress"] = 0 if result.progress else s["turns_since_progress"] + 1
        s["log"].append({"turn": s["turns"], "action": action.model_dump(), "event": result.event, "ok": result.ok})
        return result

    # ---------------------------------------------------------------- actions
    def _look(self) -> Result:
        parts = [f"You are in {self.room['title']}. You see " +
                 "; ".join(spec["description"] for spec in self.objects.values()) + "."]
        if self.state["visible_items"]:
            parts.append("Lying around: " + ", ".join(self.state["visible_items"]) + ".")
        return Result(True, "look", " ".join(parts))

    def _inventory(self) -> Result:
        inv = self.state["inventory"]
        return Result(True, "inventory", "You are carrying: " + ", ".join(inv) + "." if inv else "Your hands are empty.")

    def _hint(self) -> Result:
        return Result(True, "hint", "Hint: " + self.next_hint())

    def _other(self) -> Result:
        return Result(False, "no_effect", "Nothing in the room changes. Only actions inside the room have an effect.")

    def _examine(self, target, item, code) -> Result:
        if not target:
            return self._look()
        found = self.resolve(target)
        if found is None:
            return self._not_found(target)
        kind, name = found
        if kind == "item":
            if name in self.state["inventory"] or name in self.state["visible_items"]:
                return Result(True, "examine_item", self.items[name]["description"])
            return self._not_found(target)
        if item:
            return self._use(name, item, code)

        spec, s = self.objects[name], self.state
        first_time = name not in s["examined"]
        if first_time:
            s["examined"].append(name)
        locked = "lock" in spec and name not in s["unlocked"]
        text = spec.get("examine_locked", spec["description"]) if locked else spec.get("examine", spec["description"])
        ew = spec.get("examine_with")
        if ew and ew.get("solves") in s["solved"]:
            text = ew["text"]
        if not locked:
            newly = self._reveal(name, spec.get("reveals", []) if "lock" not in spec else [])
            here = [i for i, where in s["visible_items"].items() if where == name and i not in newly]
            if here:
                text += " Still here: " + ", ".join(here) + "."
        return Result(True, "examine", text, progress=first_time)

    def _take(self, target, item, code) -> Result:
        found = self.resolve(target or item)
        if found is None:
            return self._not_found(target or item)
        kind, name = found
        s = self.state
        if kind == "object":
            return Result(False, "cannot_take", f"You can't carry the {name}.")
        if name in s["inventory"]:
            return Result(False, "already_have", f"You already have the {name}.")
        if name not in s["visible_items"]:
            return self._not_found(target or item)
        del s["visible_items"][name]
        s["inventory"].append(name)
        return Result(True, "taken", f"You take the {name}.", progress=True)

    def _use(self, target, item, code) -> Result:
        """'use X on Y' - routed to unlock or examine-with depending on Y."""
        found = self.resolve(target)
        if found is None:
            return self._not_found(target)
        kind, name = found
        if kind == "item":
            return Result(False, "no_effect", "Nothing happens.")
        spec = self.objects[name]
        if code or ("lock" in spec and name not in self.state["unlocked"]):
            return self._unlock(name, item, code)
        held = self._held_item(item)
        if isinstance(held, Result):
            return held
        ew = spec.get("examine_with")
        if ew and ew["item"] == held:
            first = ew["solves"] not in self.state["solved"]
            if first:
                self.state["solved"].append(ew["solves"])
            if name not in self.state["examined"]:
                self.state["examined"].append(name)
            return Result(True, "examine_with", ew["text"], progress=first)
        return Result(False, "no_effect", f"Using the {held} on the {name} does nothing.")

    def _unlock(self, target, item, code) -> Result:
        found = self.resolve(target)
        if found is None:
            return self._not_found(target)
        kind, name = found
        if kind == "item":
            return Result(False, "no_effect", f"The {name} can't be unlocked.")
        spec, s = self.objects[name], self.state
        lock = spec.get("lock")
        if not lock:
            return Result(False, "not_lockable", f"There is nothing to unlock on the {name}.")
        if name in s["unlocked"]:
            return Result(False, "already_open", f"The {name} is already open.")

        if lock["type"] == "code":
            if not code:
                return Result(False, "needs_code", f"The {name} needs a 4-digit code.")
            ready = all(p in s["solved"] for p in lock.get("requires_solved", []))
            if code != lock["code"] or not ready:
                s["failed_attempts"][name] = s["failed_attempts"].get(name, 0) + 1
                # identical message whether the code or the progress is wrong - no leaks
                return Result(False, "wrong_code", f"You enter {code}. The lock flashes red and stays shut.")
        else:  # item lock
            if code:
                return Result(False, "needs_item", f"The {name} has no keypad - it has a keyhole.")
            if not item:
                if lock["item"] not in s["inventory"]:
                    return Result(False, "needs_item", f"The {name} is locked. You need something to open it.")
                item = lock["item"]
            held = self._held_item(item)
            if isinstance(held, Result):
                return held
            if held != lock["item"]:
                s["failed_attempts"][name] = s["failed_attempts"].get(name, 0) + 1
                return Result(False, "wrong_item", f"The {held} doesn't fit the {name}.")

        s["unlocked"].append(name)
        if name not in s["examined"]:
            s["examined"].append(name)
        if spec.get("solves") and spec["solves"] not in s["solved"]:
            s["solved"].append(spec["solves"])
        self._reveal(name, spec.get("reveals", []))
        if spec.get("final"):
            s["door_open"] = True
        return Result(True, "unlocked", spec["unlock_text"], escaped=bool(spec.get("final")), progress=True)

    # ---------------------------------------------------------------- helpers
    def _held_item(self, item):
        """Canonical item name if the player holds it, else a failure Result."""
        found = self.resolve(item)
        if found is None or found[0] != "item":
            return Result(False, "not_in_inventory", f"You don't have any '{item}'.")
        if found[1] not in self.state["inventory"]:
            # don't reveal the real name of an item the player hasn't discovered yet
            label = found[1] if found[1] in self.known_items() else f"any '{ARTICLES.sub('', item.lower().strip())}'"
            return Result(False, "not_in_inventory", f"You don't have {'the ' if label == found[1] else ''}{label}.")
        return found[1]

    def _reveal(self, where: str, items: list) -> list:
        s, new = self.state, []
        for i in items:
            if i not in s["inventory"] and i not in s["visible_items"]:
                s["visible_items"][i] = where
                new.append(i)
        return new

    def _not_found(self, name: str) -> Result:
        return Result(False, "not_found", f"There is no '{name}' here.")

    def _check(self, cond: str) -> bool:
        kind, _, value = cond.partition(":")
        s = self.state
        return {
            "examined": value in s["examined"],
            "unlocked": value in s["unlocked"],
            "solved": value in s["solved"],
            "has": value in s["inventory"],
        }[kind]

    def next_hint(self) -> str:
        for h in self.room["hints"]:
            if not self._check(h["unless"]):
                return h["text"]
        return "You have everything you need."

    def snapshot(self) -> dict:
        return copy.deepcopy(self.state)


def result_dict(r: Result) -> dict:
    return asdict(r)
