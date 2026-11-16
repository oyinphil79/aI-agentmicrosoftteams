from __future__ import annotations

import json

from ..llm import ChatModel
from ..prompts import load_prompt

ROUTES = {"knowledge", "it", "hr"}


class RouterAgent:
    """Intent classifier on a small/cheap deployment. Falls back to `knowledge` on bad output."""

    def __init__(self, model: ChatModel):
        self.model = model

    def route(self, query: str) -> tuple[str, str]:
        turn = self.model.complete(load_prompt("router"), query, json_mode=True)
        try:
            data = json.loads(turn.text)
            route = data.get("route", "knowledge")
            return (route if route in ROUTES else "knowledge"), data.get("reason", "")
        except (json.JSONDecodeError, AttributeError):
            return "knowledge", "router output unparseable"
