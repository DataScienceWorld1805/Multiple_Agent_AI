"""End-to-end integration test with fake providers (no real APIs)."""

from __future__ import annotations

import asyncio
import re
import time

import pytest
from src.graph.build_graph import build_graph
from src.llm import FakeLLMClient
from src.providers.arxiv_provider import FakePapersProvider
from src.providers.search_provider import FakeSearchProvider
from src.schemas.models import ResearcherStatus


@pytest.mark.asyncio
async def test_end_to_end_fake_providers(fake_settings, memory_store) -> None:
    app = build_graph(
        settings=fake_settings,
        llm=FakeLLMClient(),
        search_provider=FakeSearchProvider(),
        papers_provider=FakePapersProvider(),
        vector_store=memory_store,
    )
    state = await app.arun("Estado actual de la fusion nuclear como energia comercial?")
    report = state["report"]
    assert report is not None
    assert report.markdown
    assert (
        "Executive Summary" in report.markdown or "Research Report" in report.markdown
    )
    assert "References" in report.markdown
    assert state.get("plan") is not None
    assert len(state["plan"].subquestions) >= 2
    assert state.get("results")
    finding_ids = {f.id for r in state["results"] for f in r.findings}
    for citation in report.citations:
        assert citation.finding_id in finding_ids


@pytest.mark.asyncio
async def test_researchers_run_in_parallel(fake_settings, memory_store) -> None:
    """Verify overlapped execution via artificial async provider delays."""

    class SlowSearch(FakeSearchProvider):
        async def search(self, query: str, max_results: int = 5):
            await asyncio.sleep(0.25)
            return await super().search(query, max_results)

    class SlowPapers(FakePapersProvider):
        async def search(self, query: str, max_results: int = 5):
            await asyncio.sleep(0.25)
            return await super().search(query, max_results)

    app = build_graph(
        settings=fake_settings,
        llm=FakeLLMClient(),
        search_provider=SlowSearch(),
        papers_provider=SlowPapers(),
        vector_store=memory_store,
    )
    started = time.perf_counter()
    state = await app.arun("Parallel fusion research question")
    elapsed = time.perf_counter() - started
    # Fake plan assigns multiple web/paper workers; sequential would exceed ~1s.
    assert elapsed < 1.0
    assert any(r.status == ResearcherStatus.SUCCESS for r in state["results"])
    assert re.search(r"Research Report", state["report"].markdown)
