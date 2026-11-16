"""Adaptive Card builders (schema 1.5, Teams-compatible).

- `answer_card`: answer + citations + feedback buttons
- approval cards use `Action.Execute` (Universal Actions) so the bot can
  replace the card in place with the result after the user approves.
"""

from __future__ import annotations

from typing import Any

from ..models import AgentResponse, PendingAction

SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"
AGENT_LABEL = {"knowledge": "Policy Assistant", "it": "IT Support", "hr": "HR Assistant",
               "shield": "Safety", "reviewer": "Safety"}


def _card(body: list[dict], actions: list[dict] | None = None) -> dict[str, Any]:
    card: dict[str, Any] = {"type": "AdaptiveCard", "$schema": SCHEMA, "version": "1.5", "body": body}
    if actions:
        card["actions"] = actions
    return card


def _header(agent: str) -> dict:
    return {"type": "TextBlock", "text": AGENT_LABEL.get(agent, agent), "weight": "Bolder",
            "size": "Small", "color": "Accent", "isSubtle": True}


def answer_card(r: AgentResponse) -> dict[str, Any]:
    if r.pending_action:
        return approval_card(r.pending_action, r.text, r.agent)
    body: list[dict] = [_header(r.agent), {"type": "TextBlock", "text": r.text, "wrap": True,
                                           "color": "Attention" if r.blocked else "Default"}]
    if r.citations:
        body.append({"type": "TextBlock", "text": "Sources", "weight": "Bolder", "spacing": "Medium", "size": "Small"})
        body.append({"type": "FactSet", "facts": [
            {"title": f"[{i}]", "value": f"[{c.title}]({c.source})"} for i, c in enumerate(r.citations, 1)]})
    body.append({"type": "TextBlock", "text": "AI-generated content may be incorrect.", "size": "Small",
                 "isSubtle": True, "wrap": True})
    actions = [
        {"type": "Action.Execute", "title": "👍 Helpful", "verb": "feedback", "data": {"rating": "up"}},
        {"type": "Action.Execute", "title": "👎 Not helpful", "verb": "feedback", "data": {"rating": "down"}},
    ]
    return _card(body, actions)


def approval_card(action: PendingAction, text: str, agent: str) -> dict[str, Any]:
    facts = [{"title": k.capitalize(), "value": str(v)} for k, v in action.arguments.items()]
    body = [
        _header(agent),
        {"type": "TextBlock", "text": text, "wrap": True},
        {"type": "FactSet", "facts": facts},
    ]
    payload = {"agent": agent, "tool": action.tool, "arguments": action.arguments}
    return _card(body, [
        {"type": "Action.Execute", "title": "Approve", "verb": "approveAction", "style": "positive", "data": payload},
        {"type": "Action.Execute", "title": "Cancel", "verb": "cancelAction", "data": payload},
    ])


def result_card(text: str, agent: str, success: bool = True) -> dict[str, Any]:
    return _card([_header(agent), {"type": "TextBlock", "text": ("✅ " if success else "⛔ ") + text, "wrap": True}])
