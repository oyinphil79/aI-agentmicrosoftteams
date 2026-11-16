from __future__ import annotations

from ..llm import ChatModel, Tool
from ..tools.graph import GraphClient
from ..tools.hr import MockHrApi
from .base import ToolAgent


def hr_tools(graph: GraphClient, hr_api: MockHrApi) -> list[Tool]:
    empty = {"type": "object", "properties": {}}
    return [
        Tool("get_leave_balance", "Get the user's remaining leave balance from the HR system.", empty,
             lambda user: hr_api.leave_balance(user)),
        Tool("get_manager", "Get the user's manager from Microsoft Graph.", empty, lambda user: graph.get_manager(user)),
        Tool("get_upcoming_meetings", "Get the user's meetings for the next N days (Graph calendarView).", {
            "type": "object", "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 7}},
        }, lambda user, days=1: graph.get_upcoming_meetings(user, days)),
    ]


class HRAgent(ToolAgent):
    name = "hr"
    prompt_name = "hr"

    def __init__(self, model: ChatModel, graph: GraphClient, hr_api: MockHrApi):
        super().__init__(model, hr_tools(graph, hr_api))

    def format_result(self, tool: str, result) -> str:
        if tool == "get_leave_balance":
            return f"You have {result['annual']} days of annual leave and {result['sick']} sick days remaining."
        if tool == "get_manager":
            return f"Your manager is {result['displayName']} ({result.get('mail', '')})."
        return super().format_result(tool, result)
