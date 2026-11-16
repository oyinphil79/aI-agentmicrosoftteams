"""Multi-agent orchestration.

    user msg -> [input shield] -> Router -> {Knowledge | IT | HR} -> [Reviewer (knowledge)] -> reply

This hand-written pipeline is the reference implementation used by tests and evals.
`agent_framework_runtime.py` expresses the same graph with Microsoft Agent Framework
for hosting in Foundry Agent Service.
"""

from __future__ import annotations

import logging

from .agents.hr import HRAgent
from .agents.it import ITAgent
from .agents.knowledge import KnowledgeAgent
from .agents.reviewer import ReviewerAgent
from .agents.router import RouterAgent
from .config import Settings
from .llm import build_models
from .models import AgentResponse, PendingAction, UserContext
from .retrieval.search import build_retriever
from .safety.prompt_shield import build_shield
from .tools.graph import MockGraph, MockWorkContext
from .tools.hr import MockHrApi
from .tools.tickets import TicketStore

log = logging.getLogger("ops_copilot")

BLOCKED_MESSAGE = (
    "I can't help with that request. It looks like an attempt to change my instructions. "
    "If this is a genuine question, please rephrase it."
)


class Orchestrator:
    def __init__(self, settings: Settings | None = None, *, graph=None, tickets: TicketStore | None = None):
        self.settings = settings or Settings.from_env()
        router_model, model = build_models(self.settings)
        self.shield = build_shield(self.settings)
        self.graph = graph or MockGraph()
        self.tickets = tickets or TicketStore()
        self.router = RouterAgent(router_model)
        self.reviewer = ReviewerAgent(model)
        self.agents = {
            "knowledge": KnowledgeAgent(model, build_retriever(self.settings), self.shield,
                                        MockWorkContext() if self.settings.is_mock else None),
            "it": ITAgent(model, self.tickets),
            "hr": HRAgent(model, self.graph, MockHrApi()),
        }

    def ask(self, query: str, user: UserContext) -> AgentResponse:
        verdict = self.shield.analyze(query)
        if verdict.user_attack:
            log.warning("blocked user prompt from %s: %s", user.email, verdict.reasons)
            return AgentResponse(BLOCKED_MESSAGE, "shield", blocked=True, safety_notes=verdict.reasons,
                                 trace=["input shield: blocked"])

        route, reason = self.router.route(query)
        response = self.agents[route].handle(query, user)
        response.trace.insert(0, f"router -> {route} ({reason})")

        if route == "knowledge":
            review = self.reviewer.review(response)
            response.trace.append(f"reviewer: {review}")
            if review.get("verdict") == "block":
                return AgentResponse("I can't share that information.", "reviewer", blocked=True,
                                     safety_notes=[review.get("reason", "")], trace=response.trace)
            if review.get("verdict") == "revise":
                response.safety_notes.append("low groundedness - answer flagged for review")
        return response

    def approve(self, action: PendingAction, user: UserContext, agent: str = "it") -> AgentResponse:
        return self.agents[agent].execute_approved(action, user)
