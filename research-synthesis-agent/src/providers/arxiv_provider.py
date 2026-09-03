"""Academic paper providers (arXiv by default)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import Settings, get_settings
from src.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class PaperHit:
    """Normalized academic paper result."""

    title: str
    url: str
    abstract: str
    authors: list[str] = field(default_factory=list)
    published: str | None = None
    paper_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PapersProvider(ABC):
    """Abstract academic search interface."""

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> list[PaperHit]:
        """Search academic sources."""


class FakePapersProvider(PapersProvider):
    """Deterministic papers provider for tests."""

    def __init__(self, hits: list[PaperHit] | None = None) -> None:
        self.hits = hits or [
            PaperHit(
                title="Advances in Magnetic Confinement Fusion",
                url="https://arxiv.org/abs/0000.00001",
                abstract=(
                    "Recent tokamak experiments report improved confinement "
                    "and progress toward burning plasma conditions."
                ),
                authors=["Doe, J.", "Smith, A."],
                published="2024-01-15",
                paper_id="0000.00001",
            ),
            PaperHit(
                title="Inertial Fusion Energy Pathways",
                url="https://arxiv.org/abs/0000.00002",
                abstract=(
                    "Laser-driven inertial confinement shows path to ignition "
                    "but faces target fabrication and repetition-rate challenges."
                ),
                authors=["Lee, K."],
                published="2023-11-02",
                paper_id="0000.00002",
            ),
        ]
        self.calls: list[str] = []

    async def search(self, query: str, max_results: int = 5) -> list[PaperHit]:
        self.calls.append(query)
        return self.hits[:max_results]


class ArxivProvider(PapersProvider):
    """arXiv API-backed papers provider."""

    def __init__(self, settings: Settings) -> None:
        self._max_default = settings.arxiv_max_results
        self._timeout = settings.researcher_timeout_seconds

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def search(self, query: str, max_results: int = 5) -> list[PaperHit]:
        import asyncio

        import arxiv

        def _sync_search() -> list[PaperHit]:
            client = arxiv.Client(page_size=max_results, delay_seconds=1.0)
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance,
            )
            results: list[PaperHit] = []
            for paper in client.results(search):
                results.append(
                    PaperHit(
                        title=paper.title,
                        url=paper.entry_id,
                        abstract=paper.summary.replace("\n", " "),
                        authors=[a.name for a in paper.authors],
                        published=(
                            paper.published.date().isoformat()
                            if paper.published
                            else None
                        ),
                        paper_id=paper.get_short_id(),
                        metadata={"categories": list(paper.categories)},
                    )
                )
            return results

        return await asyncio.wait_for(
            asyncio.to_thread(_sync_search),
            timeout=self._timeout,
        )


def create_papers_provider(settings: Settings | None = None) -> PapersProvider:
    """Factory for papers providers."""
    cfg = settings or get_settings()
    provider = cfg.papers_provider.lower()
    if provider == "fake":
        return FakePapersProvider()
    if provider == "arxiv":
        return ArxivProvider(cfg)
    raise ValueError(f"Unsupported papers_provider: {cfg.papers_provider}")
