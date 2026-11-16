"""Ticketing backend. In mock mode used in-process; in production exposed via the MCP
server in `mcp_server/` (which wraps ServiceNow/Jira or this store)."""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

CATEGORIES = {"network", "hardware", "software", "access"}
PRIORITIES = {"low", "medium", "high"}


@dataclass
class Ticket:
    id: str
    title: str
    category: str
    priority: str
    requester: str
    status: str = "New"
    created: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))


class TicketStore:
    def __init__(self) -> None:
        self._seq = itertools.count(1001)
        self._tickets: dict[str, Ticket] = {}
        self.create("Monitor flickering", "hardware", "low", "alex@contoso.com", ticket_id="INC1000", status="In Progress")

    def create(self, title: str, category: str, priority: str, requester: str, *, ticket_id: str | None = None,
               status: str = "New") -> dict:
        if category not in CATEGORIES:
            raise ValueError(f"category must be one of {sorted(CATEGORIES)}")
        if priority not in PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(PRIORITIES)}")
        t = Ticket(ticket_id or f"INC{next(self._seq)}", title.strip()[:120], category, priority, requester, status)
        self._tickets[t.id] = t
        return asdict(t)

    def get(self, ticket_id: str, requester: str) -> dict | None:
        t = self._tickets.get(ticket_id)
        # Object-level authorization: users can only see their own tickets.
        return asdict(t) if t and t.requester == requester else None

    def list_for(self, requester: str) -> list[dict]:
        return [asdict(t) for t in self._tickets.values() if t.requester == requester]
