"""Least-privilege tool allow-lists per agent + per-user authorization.

Even if a prompt injection convinces a model to call a tool, the orchestrator
refuses any tool that is not on that agent's allow-list or that the user's
Entra groups do not permit.
"""

from __future__ import annotations

from ..models import UserContext

AGENT_TOOL_ALLOWLIST: dict[str, set[str]] = {
    "knowledge": set(),  # read-only RAG; no tools
    "it": {"create_ticket", "get_ticket_status", "list_my_devices"},
    "hr": {"get_leave_balance", "get_manager", "get_upcoming_meetings"},
}

# Tools that need a specific Entra group (app role) in addition to the allow-list.
TOOL_REQUIRED_GROUPS: dict[str, set[str]] = {
    "create_ticket": {"all-employees"},
}


class ToolNotPermitted(Exception):
    pass


def authorize(agent: str, tool: str, user: UserContext) -> None:
    if tool not in AGENT_TOOL_ALLOWLIST.get(agent, set()):
        raise ToolNotPermitted(f"agent '{agent}' is not allowed to call '{tool}'")
    required = TOOL_REQUIRED_GROUPS.get(tool)
    if required and not (required & set(user.groups)):
        raise ToolNotPermitted(f"user {user.email} lacks a group required for '{tool}'")
