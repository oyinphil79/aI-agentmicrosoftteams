"""Shared tool-calling loop with allow-list enforcement and human-in-the-loop for side effects."""

from __future__ import annotations

import json

from ..llm import ChatModel, Tool
from ..models import AgentResponse, PendingAction, UserContext
from ..prompts import load_prompt
from ..safety.tool_policy import ToolNotPermitted, authorize


class ToolAgent:
    name = "base"
    prompt_name = ""

    def __init__(self, model: ChatModel, tools: list[Tool]):
        self.model = model
        self.tools = {t.name: t for t in tools}

    def handle(self, query: str, user: UserContext) -> AgentResponse:
        system = load_prompt(self.prompt_name)
        turn = self.model.complete(system, f"USER: {user.display_name}\nQUESTION: {query}", tools=list(self.tools.values()))
        trace = [f"{self.name}: model turn, {len(turn.tool_calls)} tool call(s)"]
        if not turn.tool_calls:
            return AgentResponse(turn.text or "I couldn't help with that one.", self.name, trace=trace)

        call = turn.tool_calls[0]
        try:
            authorize(self.name, call.name, user)
        except ToolNotPermitted as e:
            trace.append(f"DENIED {call.name}: {e}")
            return AgentResponse("That action isn't permitted for this assistant.", self.name,
                                 safety_notes=[str(e)], trace=trace)
        tool = self.tools[call.name]
        if tool.side_effect:
            trace.append(f"{call.name} requires approval")
            return AgentResponse(
                self.describe_pending(call.name, call.arguments), self.name,
                pending_action=PendingAction(call.name, call.arguments, self.describe_pending(call.name, call.arguments)),
                trace=trace,
            )
        result = tool.fn(user=user, **call.arguments)
        trace.append(f"executed {call.name}")
        final = self.model.complete(system, f"QUESTION: {query}\nTOOL RESULT: {self.format_result(call.name, result)}")
        return AgentResponse(final.text, self.name, trace=trace)

    def execute_approved(self, action: PendingAction, user: UserContext) -> AgentResponse:
        """Called when the user clicks Approve on the Adaptive Card."""
        authorize(self.name, action.tool, user)  # re-check: card payloads come from the client
        result = self.tools[action.tool].fn(user=user, **action.arguments)
        return AgentResponse(self.format_result(action.tool, result), self.name, trace=[f"executed {action.tool} after approval"])

    def describe_pending(self, tool: str, args: dict) -> str:
        return f"I'd like to run **{tool}** with {json.dumps(args)}. Approve?"

    def format_result(self, tool: str, result) -> str:
        return json.dumps(result)
