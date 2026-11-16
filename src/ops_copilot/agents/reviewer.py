from __future__ import annotations

import json

from ..llm import ChatModel
from ..models import AgentResponse
from ..prompts import load_prompt


class ReviewerAgent:
    """Final gate: checks a knowledge answer is grounded in its sources and leaks nothing sensitive."""

    def __init__(self, model: ChatModel):
        self.model = model

    def review(self, response: AgentResponse) -> dict:
        sources = "\n".join(f"- {g}" for g in response.grounding) or "(none)"
        turn = self.model.complete(load_prompt("reviewer"), f"SOURCES:\n{sources}\nANSWER:\n{response.text}", json_mode=True)
        try:
            return json.loads(turn.text)
        except json.JSONDecodeError:
            return {"verdict": "revise", "reason": "reviewer output unparseable"}
