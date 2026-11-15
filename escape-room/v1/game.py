"""Version 1: the LLM is the whole game engine.

The full room - including every code and solution - goes into the system prompt,
and the LLM decides what succeeds and when the player has escaped. Python only
stores the conversation. This is deliberate: V2 fixes the resulting weaknesses.
"""
import json

from pydantic import BaseModel, Field

from escape_room.gemini import Gemini


class GMResponse(BaseModel):
    narration: str = Field(description="Text shown to the player")
    inventory: list[str] = Field(description="All items the player currently holds")
    solved: list[str] = Field(description="Puzzle ids solved so far")
    escaped: bool = Field(description="True only when the door was just opened")


def build_system_prompt(room: dict) -> str:
    secret = {k: room[k] for k in ("objects", "items", "puzzles", "hints")}
    return f"""You are the Game Master of a text-based escape room called "{room['title']}".

## Your role
- Narrate in second person ("You see..."), atmospheric but brief: 2-4 sentences per reply.
- React only to what the player does. Never solve puzzles for them.
- Keep the story consistent with everything that happened earlier in the conversation.

## The room (SECRET - never reveal codes or solutions directly)
{json.dumps(secret, indent=2)}

## Rules
1. Only the objects and items listed above exist. Anything else is not in the room.
2. Show an object's "examine" text only when the player examines it ("examine_locked" while it is locked).
3. Items listed in "reveals" become visible when the object is examined or unlocked; the player must take them.
4. A locked object opens ONLY with its exact code or item (see "lock"). Wrong codes fail.
5. The player can only use items that are in their inventory.
6. "examine_with" text is shown only when the player uses that item (from their inventory) on the object.
7. If the player is stuck or asks for help, give the next relevant hint without stating the answer.
8. The player escapes ONLY when they enter the correct code on the door keypad.

## Output format
Always reply with JSON containing:
- "narration": what the player sees/hears (shown to the player)
- "inventory": list of all items the player currently holds
- "solved": puzzle ids solved so far (from: {", ".join(room["puzzles"])})
- "escaped": true only when the door has just been opened with the correct code
"""


class GameV1:
    def __init__(self, room: dict, llm: Gemini):
        self.room = room
        self.llm = llm
        self.system = build_system_prompt(room)
        self.history: list[dict] = []   # sent to Gemini each turn
        self.inventory: list[str] = []
        self.solved: list[str] = []
        self.escaped = False
        self.turns = 0

    def turn(self, player_text: str) -> str:
        """Play one turn. Raises LLMError on API problems (state unchanged)."""
        pending = self.history + [{"role": "user", "text": player_text}]
        if self.llm.mock:
            reply = _mock_reply(player_text, self.inventory, self.solved)
        else:
            reply = self.llm.generate(self.system, pending, schema=GMResponse, temperature=0.7)
        # Full JSON is stored as the model turn so Gemini "remembers" its own state.
        self.history = pending + [{"role": "model", "text": reply.model_dump_json()}]
        self.inventory, self.solved = reply.inventory, reply.solved
        self.escaped = self.escaped or reply.escaped
        self.turns += 1
        return reply.narration


def _mock_reply(text: str, inv: list, solved: list) -> GMResponse:
    t = text.lower()
    if "0418" in t:
        return GMResponse(narration="(mock) The keypad flashes green. You are free!", inventory=inv, solved=solved, escaped=True)
    return GMResponse(narration=f"(mock) You try: {text}", inventory=inv, solved=solved, escaped=False)
