"""Chat model abstraction with tool calling.

`AzureChatModel` talks to an Azure OpenAI deployment in Foundry using Entra ID
(Managed Identity / DefaultAzureCredential) - no API keys.
`MockChatModel` is a deterministic stand-in so tests and evals run offline.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]
    side_effect: bool = False  # True => requires human approval before execution

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class ChatModel(Protocol):
    def complete(self, system: str, user: str, tools: list[Tool] | None = None, json_mode: bool = False) -> ModelTurn: ...


# --------------------------------------------------------------------------- Azure


class AzureChatModel:
    def __init__(self, endpoint: str, deployment: str, api_version: str = "2024-10-21"):
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AzureOpenAI

        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        )
        self._client = AzureOpenAI(
            azure_endpoint=endpoint, azure_ad_token_provider=token_provider, api_version=api_version
        )
        self._deployment = deployment

    def complete(self, system: str, user: str, tools: list[Tool] | None = None, json_mode: bool = False) -> ModelTurn:
        kwargs: dict[str, Any] = {
            "model": self._deployment,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
        }
        if tools:
            kwargs["tools"] = [t.openai_schema() for t in tools]
            kwargs["parallel_tool_calls"] = False
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        msg = self._client.chat.completions.create(**kwargs).choices[0].message
        calls = [
            ToolCall(tc.function.name, json.loads(tc.function.arguments or "{}")) for tc in (msg.tool_calls or [])
        ]
        return ModelTurn(text=msg.content or "", tool_calls=calls)


# --------------------------------------------------------------------------- Mock

_ROUTES = {
    "it": r"\b(inc\d+|vpn|laptop|password|printer|wifi|wi-fi|mfa|outlook (?:is|won't|crash)|install|software|ticket|reset|broken|monitor)\b",
    "hr": r"\b(leave|vacation|holiday|pto|days off|manager|payroll|benefit|sick|parental)\b",
}
_STOP = set("the a an is are of to for and or in on my me i do how what can you with be it this that".split())


def _tokens(text: str) -> set[str]:
    words = (w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 2)
    return {w[:-1] if w.endswith("s") and len(w) > 4 else w for w in words}  # naive plural stemming


class MockChatModel:
    """Rule-based model. Behaviour is selected by a role tag at the top of the system prompt."""

    def complete(self, system: str, user: str, tools: list[Tool] | None = None, json_mode: bool = False) -> ModelTurn:
        role = re.search(r"#\s*ROLE:\s*(\w+)", system)
        role = role.group(1).lower() if role else ""
        if role == "router":
            return ModelTurn(text=json.dumps(self._route(user)))
        if role == "reviewer":
            return ModelTurn(text=json.dumps(self._review(user)))
        if tools:
            call = self._pick_tool(user, tools)
            if call:
                return ModelTurn(tool_calls=[call])
        if role == "knowledge":
            return ModelTurn(text=self._extractive_answer(user))
        return ModelTurn(text=user.split("TOOL RESULT:", 1)[-1].strip() if "TOOL RESULT:" in user else "")

    def _route(self, user: str) -> dict[str, str]:
        q = user.lower()
        if re.search(r"what did i miss|my (emails?|inbox|messages)", q):
            return {"route": "knowledge", "reason": "personal work context (Work IQ)"}
        if re.match(r"(how do i|how can i|what is|what's|what are|is there a policy)\b", q) and not re.search(r"inc\d+", q):
            return {"route": "knowledge", "reason": "how-to / policy question"}
        personal = re.search(r"\b(my|i|me|do i|have i)\b", q)
        for route, pattern in _ROUTES.items():
            if route == "hr" and not personal:  # "how long is parental leave?" is a policy question
                continue
            if re.search(pattern, q):
                return {"route": route, "reason": f"matched {route} keywords"}
        return {"route": "knowledge", "reason": "general policy question"}

    def _pick_tool(self, user: str, tools: list[Tool]) -> ToolCall | None:
        q = user.split("QUESTION:", 1)[-1].lower()
        names = {t.name for t in tools}
        if "get_leave_balance" in names and re.search(r"leave|vacation|pto|days off|holiday", q):
            return ToolCall("get_leave_balance", {})
        if "get_manager" in names and "manager" in q:
            return ToolCall("get_manager", {})
        if "get_ticket_status" in names and (m := re.search(r"\b(INC\d+)\b", user, re.IGNORECASE)):
            return ToolCall("get_ticket_status", {"ticket_id": m.group(1).upper()})
        if "create_ticket" in names:
            category = "network" if re.search(r"vpn|wifi|wi-fi|network", q) else "hardware" if re.search(
                r"laptop|monitor|printer|broken", q) else "access" if re.search(r"password|mfa|reset", q) else "software"
            return ToolCall("create_ticket", {
                "title": user.split("QUESTION:", 1)[-1].strip()[:80],
                "category": category,
                "priority": "high" if re.search(r"urgent|asap|can't work|down", q) else "medium",
            })
        return None

    def _extractive_answer(self, prompt: str) -> str:
        question = prompt.split("QUESTION:", 1)[-1].strip()
        docs = re.findall(r'<document title="([^"]+)"[^>]*>(.*?)</document>', prompt, re.DOTALL)
        if not docs:
            return "I couldn't find this in the approved company sources, so I won't guess. Try rephrasing or ask HR/IT."
        q = _tokens(question)
        best: list[tuple[int, str, str]] = []
        for title, body in docs:
            body = body.replace("^", " ")  # undo datamarking
            for sentence in re.split(r"(?<=[.!?])\s+", body.strip()):
                score = len(q & _tokens(sentence))
                if score:
                    best.append((score, sentence.strip(), title))
        if not best:
            return "I couldn't find this in the approved company sources, so I won't guess."
        best.sort(key=lambda x: -x[0])
        top_score, _, top_doc = best[0]
        # Answer from the single best document; add a 2nd sentence only if it is nearly as relevant.
        picked = [best[0]] + [b for b in best[1:] if b[2] == top_doc and b[0] >= max(2, top_score - 1)][:1]
        return " ".join(f"{s} [{t}]" for _, s, t in picked)

    def _review(self, prompt: str) -> dict[str, Any]:
        answer = prompt.split("ANSWER:", 1)[-1]
        sources = prompt.split("SOURCES:", 1)[-1].split("ANSWER:", 1)[0]
        if re.search(r"\b\d{3}-\d{2}-\d{4}\b|salary of|\bpassword is\b", answer, re.IGNORECASE):
            return {"verdict": "block", "reason": "possible sensitive data in answer"}
        if "won't guess" in answer:
            return {"verdict": "pass", "reason": "honest refusal"}
        a, s = _tokens(answer), _tokens(sources)
        overlap = len(a & s) / max(len(a), 1)
        return {"verdict": "pass" if overlap >= 0.6 else "revise", "groundedness": round(overlap, 2)}


def build_models(settings) -> tuple[ChatModel, ChatModel]:
    """Returns (router_model, main_model). Router uses a cheaper/faster deployment."""
    if settings.is_mock:
        m = MockChatModel()
        return m, m
    return (
        AzureChatModel(settings.openai_endpoint, settings.router_deployment),
        AzureChatModel(settings.openai_endpoint, settings.chat_deployment),
    )
