"""Version 2 turn loop: parse (LLM/rules) -> validate (Python) -> narrate (LLM)."""
import json

from escape_room.gemini import Gemini
from escape_room.v2.engine import Engine, result_dict
from escape_room.v2.narrator import narrate
from escape_room.v2.parser import parse


class GameV2:
    def __init__(self, room: dict, llm: Gemini):
        self.room = room
        self.llm = llm
        self.engine = Engine(room)
        self.recent: list[dict] = []      # short narration history for tone continuity
        self.last_debug: dict = {}

    @property
    def state(self) -> dict:
        return self.engine.state

    @property
    def escaped(self) -> bool:
        return self.engine.state["door_open"]

    def turn(self, player_text: str) -> str:
        """Play one turn. Parser API errors propagate as LLMError (state unchanged)."""
        action, parsed_by = parse(player_text, self.engine, self.llm)
        result = self.engine.apply(action, player_text)

        # Nudge a stuck player with Python's hint (never the solution itself).
        if result.event != "hint" and self.engine.state["turns_since_progress"] >= 4:
            result.facts += " (A thought strikes you: " + self.engine.next_hint() + ")"
            self.engine.state["turns_since_progress"] = 0

        narration, narrated_by = narrate(player_text, result, self.engine, self.llm, self.recent)
        self.recent += [
            {"role": "user", "text": json.dumps({"player_said": player_text})},
            {"role": "model", "text": narration},
        ]
        self.last_debug = {
            "action": action.model_dump(),
            "parsed_by": parsed_by,
            "result": result_dict(result),
            "narrated_by": narrated_by,
        }
        return narration
