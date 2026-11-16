"""Enterprise grounding.

- `LocalIndex`: offline keyword index over data/policies/*.md (mock mode + tests).
- `AzureSearchRetriever`: hybrid (BM25 + vector) query with semantic ranking and
  **security trimming** on `allowed_groups`, authenticated with Managed Identity.
- `FoundryIQRetriever`: agentic retrieval through a Foundry IQ knowledge base
  (query planning + multi-source retrieval on top of Azure AI Search).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..models import UserContext


@dataclass
class Document:
    id: str
    title: str
    content: str
    source: str
    allowed_groups: tuple[str, ...] = ("all-employees",)
    score: float = 0.0


class Retriever(Protocol):
    def search(self, query: str, user: UserContext, top: int = 3) -> list[Document]: ...


def _parse_markdown(path: Path) -> Document:
    text = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    if text.startswith("---"):
        _, front, text = text.split("---", 2)
        for line in front.strip().splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    groups = tuple(g.strip() for g in meta.get("allowed_groups", "all-employees").split(",") if g.strip())
    return Document(
        id=path.stem,
        title=meta.get("title", path.stem),
        content=text.strip(),
        source=meta.get("source", f"sharepoint://policies/{path.name}"),
        allowed_groups=groups,
    )


def _tok(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2]


class LocalIndex:
    def __init__(self, *dirs: Path):
        self.docs = [_parse_markdown(p) for d in dirs if d.exists() for p in sorted(d.glob("*.md"))]

    def search(self, query: str, user: UserContext, top: int = 3) -> list[Document]:
        q = set(_tok(query))
        hits = []
        for d in self.docs:
            if not set(d.allowed_groups) & set(user.groups):  # security trimming
                continue
            words = _tok(d.title + " " + d.content)
            score = sum(words.count(t) for t in q) + 3 * len(q & set(_tok(d.title)))
            if score:
                hits.append(Document(**{**d.__dict__, "score": float(score)}))
        return sorted(hits, key=lambda d: -d.score)[:top]


class AzureSearchRetriever:
    def __init__(self, endpoint: str, index: str, semantic_config: str = "default"):
        from azure.identity import DefaultAzureCredential
        from azure.search.documents import SearchClient

        self._client = SearchClient(endpoint, index, DefaultAzureCredential())
        self._semantic = semantic_config

    def search(self, query: str, user: UserContext, top: int = 3) -> list[Document]:
        from azure.search.documents.models import VectorizableTextQuery

        groups = ",".join(g.replace("'", "") for g in user.groups)
        results = self._client.search(
            search_text=query,
            vector_queries=[VectorizableTextQuery(text=query, k_nearest_neighbors=20, fields="content_vector")],
            query_type="semantic",
            semantic_configuration_name=self._semantic,
            filter=f"allowed_groups/any(g: search.in(g, '{groups}', ','))",
            select=["id", "title", "content", "source", "allowed_groups"],
            top=top,
        )
        return [
            Document(r["id"], r["title"], r["content"], r["source"], tuple(r.get("allowed_groups") or ()),
                     r.get("@search.reranker_score") or r.get("@search.score", 0.0))
            for r in results
        ]


class FoundryIQRetriever:
    """Agentic retrieval via a Foundry IQ knowledge base (preview REST API).

    NOTE: preview API - confirm the api-version and payload against current docs before use.
    The user's token is forwarded so the knowledge base can enforce document-level permissions.
    """

    def __init__(self, search_endpoint: str, knowledge_base: str, api_version: str = "2025-11-01-preview"):
        import httpx
        from azure.identity import DefaultAzureCredential

        self._url = f"{search_endpoint.rstrip('/')}/knowledgebases/{knowledge_base}/retrieve"
        self._api_version = api_version
        self._cred = DefaultAzureCredential()
        self._http = httpx.Client(timeout=30)

    def search(self, query: str, user: UserContext, top: int = 3) -> list[Document]:
        headers = {"Authorization": f"Bearer {self._cred.get_token('https://search.azure.com/.default').token}"}
        if user.access_token:
            headers["x-ms-query-source-authorization"] = user.access_token
        r = self._http.post(
            self._url, params={"api-version": self._api_version}, headers=headers,
            json={"messages": [{"role": "user", "content": [{"type": "text", "text": query}]}]},
        )
        r.raise_for_status()
        refs = r.json().get("references", [])[:top]
        return [
            Document(str(ref.get("id")), ref.get("sourceData", {}).get("title", "source"),
                     ref.get("sourceData", {}).get("content", ""), ref.get("docKey", ""))
            for ref in refs
        ]


def build_retriever(settings) -> Retriever:
    if settings.is_mock:
        return LocalIndex(settings.data_dir / "policies", settings.data_dir / "injection")
    return AzureSearchRetriever(settings.search_endpoint, settings.search_index)
