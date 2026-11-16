"""Loads versioned `.prompty` files (YAML front matter + system prompt body)."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from .config import Settings


@cache
def load_prompt(name: str, prompts_dir: Path | None = None) -> str:
    path = (prompts_dir or Settings().prompts_dir) / f"{name}.prompty"
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        _, _front, body = text.split("---", 2)
        return body.strip()
    return text.strip()
