from __future__ import annotations

from ..llm import ChatModel, Tool
from ..models import UserContext
from ..tools.tickets import TicketStore
from .base import ToolAgent


def it_tools(store: TicketStore) -> list[Tool]:
    def create_ticket(user: UserContext, title: str, category: str, priority: str = "medium") -> dict:
        return store.create(title, category, priority, requester=user.email)

    def get_ticket_status(user: UserContext, ticket_id: str) -> dict:
        return store.get(ticket_id, user.email) or {"error": f"No ticket {ticket_id} found for you"}

    def list_my_devices(user: UserContext) -> list[dict]:
        return [{"name": "CONTOSO-LT-4821", "model": "Surface Laptop 6", "compliant": True}]

    return [
        Tool("create_ticket", "Open an IT support ticket for the current user.", {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short summary of the problem"},
                "category": {"type": "string", "enum": ["network", "hardware", "software", "access"]},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["title", "category"],
        }, create_ticket, side_effect=True),
        Tool("get_ticket_status", "Look up one of the user's IT tickets by ID (e.g. INC1000).", {
            "type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"],
        }, get_ticket_status),
        Tool("list_my_devices", "List devices registered to the user in Intune.", {"type": "object", "properties": {}},
             list_my_devices),
    ]


class ITAgent(ToolAgent):
    name = "it"
    prompt_name = "it"

    def __init__(self, model: ChatModel, store: TicketStore):
        super().__init__(model, it_tools(store))

    def describe_pending(self, tool: str, args: dict) -> str:
        if tool == "create_ticket":
            return (f"I can open a **{args.get('priority', 'medium')}** priority **{args.get('category')}** ticket: "
                    f"\"{args.get('title')}\". Shall I submit it?")
        return super().describe_pending(tool, args)

    def format_result(self, tool: str, result) -> str:
        if tool == "create_ticket":
            return f"Ticket {result['id']} created ({result['category']}, {result['priority']}). Status: {result['status']}."
        if tool == "get_ticket_status" and "id" in result:
            return f"Ticket {result['id']} \"{result['title']}\" is {result['status']}."
        return super().format_result(tool, result)
