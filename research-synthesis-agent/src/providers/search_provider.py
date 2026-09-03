"""Web search provider interface and implementations."""

from __future__ import annotations

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
        self.hits = hits or [
            SearchHit(
                title="Example Web Result on Nuclear Fusion",
                url="https://example.com/fusion-status",
                snippet=(
                    "Commercial fusion remains pre-commercial; several pilots "
                    "target net energy demonstrations this decade."
                ),
                score=0.9,
            ),
            SearchHit(
                title="IEA Fusion Outlook",
                url="https://example.com/iea-fusion",
                snippet=(
                    "Economic viability depends on materials, tritium supply, "
                    "and sustained high gain."
                ),
                score=0.8,
            ),
        ]
        self.calls: list[str] = []

    async def search(self, query: str, max_results: int = 5) -> list[SearchHit]:
        self.calls.append(query)
        return self.hits[:max_results]


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
            hits.append(
                SearchHit(
                    title=item.get("title") or "Untitled",
                    url=item.get("url") or "",
                    snippet=item.get("content") or item.get("snippet") or "",
                    score=float(item.get("score") or 0.5),
                    metadata={"raw": item},
                )
            )
        return hits


def create_search_provider(settings: Settings | None = None) -> SearchProvider:
    """Factory for search providers."""
    cfg = settings or get_settings()
    provider = cfg.search_provider.lower()
    if provider == "fake":
        return FakeSearchProvider()
    if provider == "tavily":
        return TavilySearchProvider(cfg)
    raise ValueError(f"Unsupported search_provider: {cfg.search_provider}")
