"""Pydantic models shared across orchestrator, researchers, and synthesizer."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class SourceType(StrEnum):
    """Type of research source / researcher worker."""

    WEB = "web"
    PAPER = "paper"
    INTERNAL_KB = "internal_kb"


class ResearcherStatus(StrEnum):
    """Outcome status of a researcher run."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    INSUFFICIENT = "insufficient"


class SubQuestion(BaseModel):
    """Independent investigable sub-question produced by the orchestrator."""

    id: str = Field(..., description="Stable identifier, e.g. sq-1")
    question: str = Field(..., min_length=1)
    rationale: str = Field(..., description="Why this sub-question matters")
    assigned_sources: list[SourceType] = Field(
        ...,
        min_length=1,
        description="Researchers assigned to this sub-question",
    )
    priority: int = Field(default=1, ge=1)


class ResearchPlan(BaseModel):
    """Explicit research plan inspectable via logs."""

    original_query: str
    subquestions: list[SubQuestion] = Field(..., min_length=2)
    max_subquestions: int = Field(..., ge=2)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )


class Finding(BaseModel):
    """Structured finding returned by a researcher."""

    id: str
    subquestion_id: str
    claim: str
    evidence: str
    source_title: str
    source_url: str | None = None
    source_type: SourceType
    confidence: float = Field(ge=0.0, le=1.0)
    relevance: float = Field(ge=0.0, le=1.0)
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearcherResult(BaseModel):
    """Structured output contract shared by all researcher workers."""

    researcher_type: SourceType
    subquestion_id: str
    findings: list[Finding] = Field(default_factory=list)
    status: ResearcherStatus
    error_message: str | None = None
    duration_ms: float = Field(ge=0.0)
    token_usage: int | None = None


class Contradiction(BaseModel):
    """Explicit contradiction between findings."""

    topic: str
    finding_ids: list[str] = Field(..., min_length=2)
    description: str


class ReportSection(BaseModel):
    """One report section aligned to a sub-question."""

    subquestion_id: str
    title: str
    content: str
    finding_ids: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    """Numbered citation tied to a real Finding id."""

    number: int = Field(ge=1)
    finding_id: str
    title: str
    url: str | None = None
    source_type: SourceType


class FinalReport(BaseModel):
    """Final synthesis report with citations and limitations."""

    query: str
    executive_summary: str
    sections: list[ReportSection] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    markdown: str = ""


def merge_results(
    existing: list[ResearcherResult] | None,
    new: list[ResearcherResult] | ResearcherResult,
) -> list[ResearcherResult]:
    """Reducer that appends researcher results into graph state."""
    base = list(existing or [])
    if isinstance(new, list):
        base.extend(new)
    else:
        base.append(new)
    return base


class GraphState(TypedDict):
    """LangGraph shared state (TypedDict for reducer compatibility)."""

    query: str
    plan: ResearchPlan | None
    results: Annotated[list[ResearcherResult], merge_results]
    report: FinalReport | None
    errors: list[str]
    retry_count: int
