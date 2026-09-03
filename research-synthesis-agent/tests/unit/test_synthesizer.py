"""Unit tests for synthesizer."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from src.agents.synthesizer import Synthesizer
from src.llm import FakeLLMClient
from src.schemas.models import (
    Finding,
    ResearcherResult,
    ResearcherStatus,
    ResearchPlan,
    SourceType,
    SubQuestion,
)


@pytest.mark.asyncio
async def test_synthesizer_grounded_citations(fake_settings) -> None:
    finding = Finding(
        id="f-web-1",
        subquestion_id="sq-1",
        claim="Fusion is pre-commercial",
        evidence="Pilots ongoing",
        source_title="Example",
        source_url="https://example.com/a",
        source_type=SourceType.WEB,
        confidence=0.9,
        relevance=0.9,
        retrieved_at=datetime.now(UTC),
    )
    plan = ResearchPlan(
        original_query="fusion?",
        subquestions=[
            SubQuestion(
                id="sq-1",
                question="status?",
                rationale="r",
                assigned_sources=[SourceType.WEB],
            ),
            SubQuestion(
                id="sq-2",
                question="barriers?",
                rationale="r",
                assigned_sources=[SourceType.PAPER],
            ),
        ],
        max_subquestions=5,
    )
    results = [
        ResearcherResult(
            researcher_type=SourceType.WEB,
            subquestion_id="sq-1",
            findings=[finding],
            status=ResearcherStatus.SUCCESS,
            duration_ms=10.0,
        ),
        ResearcherResult(
            researcher_type=SourceType.PAPER,
            subquestion_id="sq-2",
            findings=[],
            status=ResearcherStatus.INSUFFICIENT,
            error_message="none",
            duration_ms=5.0,
        ),
    ]
    synth = Synthesizer(fake_settings, FakeLLMClient())
    report = await synth.synthesize("fusion?", plan, results)
    assert report.citations
    assert report.citations[0].finding_id == "f-web-1"
    assert report.citations[0].url == "https://example.com/a"
    assert "[1]" in report.markdown or "References" in report.markdown
    assert report.limitations
    assert all(c.finding_id == "f-web-1" for c in report.citations)
