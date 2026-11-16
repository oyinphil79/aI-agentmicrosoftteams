"""Runtime settings, read from environment variables.

`mode="mock"` wires every dependency to an in-process fake so the whole system
(agents, orchestration, safety, evals) runs offline. `mode="azure"` wires real
Foundry / Azure OpenAI / AI Search / Graph / Content Safety clients.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    mode: str = "mock"
    openai_endpoint: str = ""
    chat_deployment: str = "gpt-4.1"
    router_deployment: str = "gpt-4.1-mini"
    project_endpoint: str = ""
    search_endpoint: str = ""
    search_index: str = "policies"
    content_safety_endpoint: str = ""
    tickets_mcp_url: str = "http://localhost:8765/mcp"
    data_dir: Path = field(default=REPO_ROOT / "data")
    prompts_dir: Path = field(default=REPO_ROOT / "prompts")

    @property
    def is_mock(self) -> bool:
        return self.mode == "mock"

    @classmethod
    def from_env(cls) -> Settings:
        e = os.environ.get
        return cls(
            mode=e("OPS_COPILOT_MODE", "mock"),
            openai_endpoint=e("AZURE_OPENAI_ENDPOINT", ""),
            chat_deployment=e("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4.1"),
            router_deployment=e("AZURE_OPENAI_ROUTER_DEPLOYMENT", "gpt-4.1-mini"),
            project_endpoint=e("AZURE_AI_PROJECT_ENDPOINT", ""),
            search_endpoint=e("AZURE_SEARCH_ENDPOINT", ""),
            search_index=e("AZURE_SEARCH_INDEX", "policies"),
            content_safety_endpoint=e("AZURE_CONTENT_SAFETY_ENDPOINT", ""),
            tickets_mcp_url=e("TICKETS_MCP_URL", "http://localhost:8765/mcp"),
        )
