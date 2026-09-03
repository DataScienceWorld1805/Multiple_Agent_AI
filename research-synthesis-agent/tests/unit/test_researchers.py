"""Unit tests for researcher workers."""

from __future__ import annotations

import pytest
from src.agents.researchers.internal_kb_researcher import InternalKBResearcher
from src.agents.researchers.papers_researcher import PapersResearcher
from src.agents.researchers.web_researcher import WebResearcher
from src.schemas.models import ResearcherStatus, SourceType, SubQuestion


def _sq() -> SubQuestion:
    return SubQuestion(
        id="sq-1",
        question="commercial nuclear fusion status",
        rationale="test",
        assigned_sources=[SourceType.WEB, SourceType.PAPER, SourceType.INTERNAL_KB],
    )


@pytest.mark.asyncio
async def test_web_researcher(fake_settings, fake_search) -> None:
    researcher = WebResearcher(fake_settings, fake_search)
    result = await researcher.research(_sq())
    assert result.researcher_type == SourceType.WEB
    assert result.status == ResearcherStatus.SUCCESS
    assert result.findings
    assert all(f.source_url for f in result.findings)
    assert fake_search.calls


@pytest.mark.asyncio
async def test_papers_researcher(fake_settings, fake_papers) -> None:
    researcher = PapersResearcher(fake_settings, fake_papers)
    result = await researcher.research(_sq())
    assert result.researcher_type == SourceType.PAPER
    assert result.status == ResearcherStatus.SUCCESS
    assert result.findings
    assert fake_papers.calls


@pytest.mark.asyncio
async def test_internal_kb_researcher(fake_settings, memory_store) -> None:
    researcher = InternalKBResearcher(fake_settings, memory_store)
    result = await researcher.research(_sq())
    assert result.researcher_type == SourceType.INTERNAL_KB
    assert result.status == ResearcherStatus.SUCCESS
    assert result.findings
    assert result.findings[0].source_url.startswith("kb://")


@pytest.mark.asyncio
async def test_web_researcher_handles_provider_failure(fake_settings) -> None:
    class BoomSearch:
        async def search(self, query: str, max_results: int = 5):
            raise RuntimeError("provider down")

    researcher = WebResearcher(fake_settings, BoomSearch())  # type: ignore[arg-type]
    result = await researcher.research(_sq())
    assert result.status == ResearcherStatus.FAILED
    assert "provider down" in (result.error_message or "")
