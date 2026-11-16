"""Shared data types passed between channels, agents and the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UserContext:
    """The signed-in user, resolved from the Teams/Outlook activity + Entra ID token.

    `groups` drive security trimming in search and per-tool authorization.
    `access_token` is the user's token, exchanged on-behalf-of for Graph/Search.
    """

    user_id: str
    display_name: str
    email: str
    groups: tuple[str, ...] = ("all-employees",)
    access_token: str | None = None


@dataclass(frozen=True)
class Citation:
    title: str
    source: str
    snippet: str = ""


@dataclass
class PendingAction:
    """A side-effecting tool call that needs explicit user approval (human-in-the-loop).

    Rendered as an Adaptive Card with Approve / Cancel buttons; executed only
    after the user clicks Approve (Action.Execute round-trip).
    """

    tool: str
    arguments: dict[str, Any]
    summary: str


@dataclass
class AgentResponse:
    text: str
    agent: str
    citations: list[Citation] = field(default_factory=list)
    pending_action: PendingAction | None = None
    blocked: bool = False
    safety_notes: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    grounding: list[str] = field(default_factory=list)  # full source text the answer was built from
