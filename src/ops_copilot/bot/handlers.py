"""Channel-agnostic handlers: pure functions so they are unit-testable without the SDK."""

from __future__ import annotations

from typing import Any

from ..cards import answer_card, result_card
from ..models import PendingAction, UserContext
from ..orchestrator import Orchestrator
from ..safety.tool_policy import ToolNotPermitted


def handle_message(orch: Orchestrator, text: str, user: UserContext) -> dict[str, Any]:
    return answer_card(orch.ask(text, user))


def handle_card_action(orch: Orchestrator, verb: str, data: dict[str, Any], user: UserContext) -> dict[str, Any]:
    if verb == "feedback":
        # Production: write to App Insights / Foundry tracing as a user-feedback signal for evals.
        return result_card("Thanks for the feedback!", "knowledge")
    if verb == "cancelAction":
        return result_card("Cancelled - nothing was submitted.", data.get("agent", "it"), success=False)
    if verb == "approveAction":
        action = PendingAction(data["tool"], dict(data.get("arguments", {})), "")
        try:
            r = orch.approve(action, user, data.get("agent", "it"))
        except (ToolNotPermitted, KeyError, ValueError) as e:  # card data is client-supplied: re-validate
            return result_card(f"Action rejected: {e}", data.get("agent", "it"), success=False)
        return result_card(r.text, r.agent)
    return result_card(f"Unknown action '{verb}'", "it", success=False)
