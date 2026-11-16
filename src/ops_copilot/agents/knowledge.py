from __future__ import annotations

import re

from ..llm import ChatModel
from ..models import AgentResponse, Citation, UserContext
from ..prompts import load_prompt
from ..retrieval.search import Document, Retriever
from ..safety.prompt_shield import PromptShield, spotlight
from ..tools.graph import WorkContext

_PERSONAL = re.compile(r"\b(i missed|my (emails?|inbox|meetings?|messages)|what did i miss)\b", re.IGNORECASE)


class KnowledgeAgent:
    """RAG agent grounded on Azure AI Search / Foundry IQ (+ Work IQ for personal context).

    Indirect prompt-injection defences:
      1. every retrieved document is screened by Prompt Shields; flagged docs are dropped
      2. surviving docs are spotlighted (datamarked) and wrapped in <document> tags
      3. the system prompt instructs the model to treat document text as data only
    """

    name = "knowledge"

    def __init__(self, model: ChatModel, retriever: Retriever, shield: PromptShield, work: WorkContext | None = None):
        self.model, self.retriever, self.shield, self.work = model, retriever, shield, work

    def gather(self, query: str, user: UserContext) -> tuple[list[Document], list[str]]:
        docs = self.retriever.search(query, user, top=3)
        if self.work and _PERSONAL.search(query):
            docs += [Document(f"work-{i}", w["title"], w["content"], w["source"]) for i, w in enumerate(self.work.search(user, query))]
        verdict = self.shield.analyze(query, [d.content for d in docs])
        notes = []
        clean = []
        for doc, attacked in zip(docs, verdict.document_attacks or [False] * len(docs), strict=True):
            if attacked:
                notes.append(f"dropped document '{doc.title}' ({doc.source}): indirect prompt injection detected")
            else:
                clean.append(doc)
        return clean, notes

    def handle(self, query: str, user: UserContext) -> AgentResponse:
        docs, notes = self.gather(query, user)
        context = "\n".join(
            f'<document title="{d.title}" source="{d.source}">{spotlight(d.content)}</document>' for d in docs
        )
        turn = self.model.complete(load_prompt("knowledge"), f"{context}\n\nQUESTION: {query}")
        used = [d for d in docs if f"[{d.title}]" in turn.text]
        return AgentResponse(
            text=turn.text,
            agent=self.name,
            citations=[Citation(d.title, d.source, d.content[:160]) for d in used],
            grounding=[f"{d.title}: {d.content}" for d in used],
            safety_notes=notes,
            trace=[f"knowledge: {len(docs)} grounded doc(s), {len(notes)} dropped"],
        )
