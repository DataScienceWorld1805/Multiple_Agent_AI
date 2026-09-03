"""Web search provider interface and implementations."""

from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import Settings, get_settings
from src.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class SearchHit:
    """Normalized search result."""

    title: str
    url: str
    snippet: str
    score: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)


class SearchProvider(ABC):
    """Abstract web search connector."""

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> list[SearchHit]:
        """Execute a web search and return normalized hits."""


class FakeSearchProvider(SearchProvider):
    """Deterministic search provider for tests and offline mode."""

    def __init__(self, hits: list[SearchHit] | None = None) -> None:
        self.hits = hits
        self.calls: list[str] = []

    async def search(self, query: str, max_results: int = 5) -> list[SearchHit]:
        self.calls.append(query)
        if self.hits is not None:
            return self.hits[:max_results]
        # Query-aware placeholders so offline demos stay on-topic.
        slug = re.sub(r"\s+", "-", query.strip().lower())[:48] or "query"
        return [
            SearchHit(
                title=f"Guía relacionada: {query[:80]}",
                url=f"https://example.com/search/{slug}",
                snippet=(
                    f"Resumen de referencia alineado con la consulta «{query[:120]}». "
                    "Modo fake: sustituir por resultados reales con "
                    "SEARCH_PROVIDER=duckduckgo o tavily."
                ),
                score=0.85,
            ),
            SearchHit(
                title=f"Manual / procedimiento: {query[:60]}",
                url=f"https://example.com/manual/{slug}",
                snippet=(
                    "Pasos, buenas prácticas y criterios de redacción asociados "
                    "al tema consultado (resultado sintético de modo offline)."
                ),
                score=0.75,
            ),
        ][:max_results]


class DuckDuckGoSearchProvider(SearchProvider):
    """Web search via DuckDuckGo (no API key required)."""

    def __init__(self, settings: Settings) -> None:
        self._timeout = settings.researcher_timeout_seconds

    async def search(self, query: str, max_results: int = 5) -> list[SearchHit]:
        def _run() -> list[dict[str, Any]]:
            try:
                from duckduckgo_search import DDGS
            except ImportError:  # pragma: no cover
                from ddgs import DDGS  # type: ignore[no-redef]

            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))

        raw = await asyncio.wait_for(asyncio.to_thread(_run), timeout=self._timeout)
        hits: list[SearchHit] = []
        for idx, item in enumerate(raw):
            title = str(item.get("title") or "Untitled").strip()
            url = str(item.get("href") or item.get("link") or "").strip()
            snippet = str(item.get("body") or item.get("snippet") or "").strip()
            if not url:
                continue
            relevance = _query_overlap_score(query, f"{title} {snippet}")
            hits.append(
                SearchHit(
                    title=title,
                    url=url,
                    snippet=snippet,
                    score=max(0.35, relevance),
                    metadata={"provider": "duckduckgo", "rank": idx + 1},
                )
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:max_results]


class TavilySearchProvider(SearchProvider):
    """Tavily Search API implementation."""

    def __init__(self, settings: Settings) -> None:
        if not settings.tavily_api_key:
            raise ValueError("TAVILY_API_KEY is required for search_provider=tavily")
        self._api_key = settings.tavily_api_key
        self._timeout = settings.researcher_timeout_seconds

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def search(self, query: str, max_results: int = 5) -> list[SearchHit]:
        import httpx

        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "include_answer": False,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        hits: list[SearchHit] = []
        for item in data.get("results", []):
            title = item.get("title") or "Untitled"
            url = item.get("url") or ""
            snippet = item.get("content") or item.get("snippet") or ""
            base = float(item.get("score") or 0.5)
            relevance = _query_overlap_score(query, f"{title} {snippet}")
            hits.append(
                SearchHit(
                    title=title,
                    url=url,
                    snippet=snippet,
                    score=max(base, relevance),
                    metadata={"raw": item, "provider": "tavily"},
                )
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits


def _query_overlap_score(query: str, text: str) -> float:
    """Lightweight relevance score based on meaningful token overlap."""
    stop = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "what",
        "cual",
        "cómo",
        "como",
        "para",
        "una",
        "unos",
        "unas",
        "del",
        "los",
        "las",
        "por",
        "con",
        "sobre",
    }
    q_tokens = {
        t
        for t in re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ0-9]{3,}", query.lower())
        if t not in stop
    }
    if not q_tokens:
        return 0.5
    hay = text.lower()
    overlap = sum(1 for t in q_tokens if t in hay)
    return min(1.0, overlap / max(len(q_tokens), 1))


def create_search_provider(settings: Settings | None = None) -> SearchProvider:
    """Factory for search providers."""
    cfg = settings or get_settings()
    provider = cfg.search_provider.lower()
    if provider == "fake":
        return FakeSearchProvider()
    if provider in {"duckduckgo", "ddg"}:
        return DuckDuckGoSearchProvider(cfg)
    if provider == "tavily":
        return TavilySearchProvider(cfg)
    raise ValueError(f"Unsupported search_provider: {cfg.search_provider}")
