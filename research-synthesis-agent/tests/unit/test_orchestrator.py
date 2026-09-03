"""Unit tests for orchestrator."""

from __future__ import annotations

import pytest
from src.agents.orchestrator import Orchestrator
from src.llm import FakeLLMClient
from src.schemas.models import ResearcherResult, ResearcherStatus, SourceType


@pytest.mark.asyncio
async def test_orchestrator_creates_plan(fake_settings) -> None:
    orch = Orchestrator(fake_settings, FakeLLMClient())
    plan = await orch.create_plan("What is the status of commercial fusion?")
    assert len(plan.subquestions) >= 2
    assert plan.original_query.startswith("What is the status")
    for sq in plan.subquestions:
        assert sq.assigned_sources
        assert sq.question


@pytest.mark.asyncio
async def test_orchestrator_reformulate_on_weak_results(fake_settings) -> None:
    llm = FakeLLMClient(
        responses={
            "Reformulate": (
                '{"subquestions":[{"id":"sq-1","question":"Refined technical status?",'
                '"rationale":"clearer","assigned_sources":["web"],"priority":1}]}'
            )
        }
    )
    orch = Orchestrator(fake_settings, llm)
    plan = await orch.create_plan("fusion?")
    weak = [
        ResearcherResult(
            researcher_type=SourceType.WEB,
            subquestion_id=plan.subquestions[0].id,
            findings=[],
            status=ResearcherStatus.INSUFFICIENT,
            error_message="none",
            duration_ms=1.0,
        )
    ]
    new_plan = await orch.maybe_reformulate(plan, weak)
    assert new_plan is not None
    assert new_plan.subquestions[0].question == "Refined technical status?"
