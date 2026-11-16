"""MCP server exposing the ticketing + asset system to agents (Foundry Agent Service, Copilot Studio,
Agent Framework, VS Code...).

Run:  python -m mcp_server.server        (streamable HTTP on :8765/mcp, mcp>=2)

Security:
- Deployed behind Azure API Management / Container Apps with Entra ID auth; the caller's
  user identity arrives as a validated token and becomes `requester`. Agents cannot choose
  whose tickets they read - see `_requester()`.
- Tools are narrowly scoped (no generic "query" tool), validated, and side-effecting tools
  are annotated so hosts can require approval.
"""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ops_copilot.tools.tickets import TicketStore

mcp = MCPServer("contoso-itsm", instructions="Contoso IT service management: tickets for the calling user only.")
store = TicketStore()


def _requester() -> str:
    # Production: derive from the validated Entra ID access token on the request (oid/upn claim).
    return os.environ.get("MCP_DEMO_USER", "alex@contoso.com")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False))
def create_ticket(title: str, category: str, priority: str = "medium") -> dict:
    """Open an IT ticket for the calling user. category: network|hardware|software|access. priority: low|medium|high."""
    return store.create(title, category, priority, requester=_requester())


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_ticket_status(ticket_id: str) -> dict:
    """Get one of the calling user's tickets by ID, e.g. INC1000."""
    return store.get(ticket_id.upper(), _requester()) or {"error": "not found"}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_my_tickets() -> list[dict]:
    """List the calling user's tickets."""
    return store.list_for(_requester())


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.environ.get("MCP_PORT", "8765")))
