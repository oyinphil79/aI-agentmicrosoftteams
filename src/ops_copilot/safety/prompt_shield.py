"""Prompt-injection detection for user input (direct) and retrieved documents (indirect).

`AzurePromptShield` calls Azure AI Content Safety Prompt Shields with Entra ID auth.
`HeuristicShield` is an offline fallback / defence-in-depth layer; it runs in both modes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ShieldResult:
    user_attack: bool = False
    document_attacks: list[bool] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def any_attack(self) -> bool:
        return self.user_attack or any(self.document_attacks)


class PromptShield(Protocol):
    def analyze(self, user_prompt: str, documents: list[str] | None = None) -> ShieldResult: ...


_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|rules|prompts?)",
    r"disregard (your|the|all) (instructions|rules|system prompt)",
    r"you are now (?!able)",  # role hijack ("you are now DAN")
    r"(reveal|print|show|repeat) (your|the) (system prompt|instructions|hidden)",
    r"\bjailbreak\b|\bDAN mode\b|developer mode",
    r"(send|email|forward|post) .{0,60}(all|every) .{0,40}(salar|password|employee|record|data)",
    r"<\s*/?\s*(system|assistant)\s*>",
    r"new instructions\s*:",
]
_RX = re.compile("|".join(_PATTERNS), re.IGNORECASE)


class HeuristicShield:
    def analyze(self, user_prompt: str, documents: list[str] | None = None) -> ShieldResult:
        res = ShieldResult()
        if m := _RX.search(user_prompt):
            res.user_attack = True
            res.reasons.append(f"user prompt matched '{m.group(0)}'")
        for i, doc in enumerate(documents or []):
            hit = _RX.search(doc)
            res.document_attacks.append(bool(hit))
            if hit:
                res.reasons.append(f"document {i} matched '{hit.group(0)}'")
        return res


class AzurePromptShield:
    API_VERSION = "2024-09-01"

    def __init__(self, endpoint: str):
        import httpx
        from azure.identity import DefaultAzureCredential

        self._endpoint = endpoint.rstrip("/")
        self._cred = DefaultAzureCredential()
        self._http = httpx.Client(timeout=10)
        self._fallback = HeuristicShield()

    def analyze(self, user_prompt: str, documents: list[str] | None = None) -> ShieldResult:
        token = self._cred.get_token("https://cognitiveservices.azure.com/.default").token
        r = self._http.post(
            f"{self._endpoint}/contentsafety/text:shieldPrompt",
            params={"api-version": self.API_VERSION},
            headers={"Authorization": f"Bearer {token}"},
            json={"userPrompt": user_prompt, "documents": documents or []},
        )
        r.raise_for_status()
        body = r.json()
        res = ShieldResult(
            user_attack=body.get("userPromptAnalysis", {}).get("attackDetected", False),
            document_attacks=[d.get("attackDetected", False) for d in body.get("documentsAnalysis", [])],
        )
        if res.any_attack:
            res.reasons.append("Azure Prompt Shields detected an attack")
        # Defence in depth: OR with local heuristics.
        local = self._fallback.analyze(user_prompt, documents)
        res.user_attack |= local.user_attack
        # Fail closed: a document without an Azure verdict is treated as an attack.
        remote = res.document_attacks + [True] * (len(local.document_attacks) - len(res.document_attacks))
        res.document_attacks = [a or b for a, b in zip(remote, local.document_attacks, strict=False)]
        res.reasons += local.reasons
        return res


def spotlight(text: str) -> str:
    """Datamarking (Microsoft 'spotlighting'): interleave a marker so the model can tell
    untrusted retrieved content from instructions. The system prompt explains the marker."""
    return "^".join(text.split(" "))


def build_shield(settings) -> PromptShield:
    if settings.is_mock or not settings.content_safety_endpoint:
        return HeuristicShield()
    return AzurePromptShield(settings.content_safety_endpoint)
