"""Orchestrator agent: decomposes queries into a research plan."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.config import Settings, get_settings
from src.llm import LLMClient, create_llm_client, extract_json_object
from src.logging_utils import get_logger, log_step
from src.schemas.models import (
    ResearcherResult,
    ResearcherStatus,
    ResearchPlan,
    SourceType,
    SubQuestion,
)

logger = get_logger(__name__)

DECOMPOSE_SYSTEM = """You are a research orchestrator. Decompose the user question into
independent investigable sub-questions for parallel research.

Return ONLY valid JSON with this shape:
{
  "subquestions": [
    {
      "id": "sq-1",
      "question": "...",
      "rationale": "...",
      "assigned_sources": ["web"|"paper"|"internal_kb", ...],
      "priority": 1
    }
  ]
}

Rules:
- Produce between MIN_SUB and MAX_SUB sub-questions.
- Sub-questions must be independently investigable.
- Assign each to the most relevant source types (one or more).
- Prefer covering web, paper, and internal_kb across the plan when relevant.
"""


class Orchestrator:
    """Plans research by decomposing a complex query into sub-questions."""

    def __init__(
        self,
        settings: Settings | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm = llm or create_llm_client(self.settings)

    async def create_plan(self, query: str) -> ResearchPlan:
        """Decompose query into an explicit ResearchPlan."""
        with log_step(logger, agent="Orchestrator", message="create_plan"):
            system = DECOMPOSE_SYSTEM.replace(
                "MIN_SUB",
                str(self.settings.min_subquestions),
            ).replace(
                "MAX_SUB",
                str(self.settings.max_subquestions),
            )
            user = f"User question:\n{query}"
            raw = await self.llm.complete(system, user)
            plan = self._parse_plan(query, raw)
            logger.info(
                "Research plan created",
                extra={
                    "agent": "Orchestrator",
                    "extra": {
                        "n_subquestions": len(plan.subquestions),
                        "plan": plan.model_dump(mode="json"),
                    },
                },
            )
            return plan

    def _parse_plan(self, query: str, raw: str) -> ResearchPlan:
        data = extract_json_object(raw)
        items = data.get("subquestions") or []
        subquestions: list[SubQuestion] = []
        for idx, item in enumerate(items, start=1):
            sources = [
                SourceType(s) if not isinstance(s, SourceType) else s
                for s in item.get("assigned_sources") or [SourceType.WEB]
            ]
            subquestions.append(
                SubQuestion(
                    id=item.get("id") or f"sq-{idx}",
                    question=item["question"],
                    rationale=item.get("rationale") or "N/A",
                    assigned_sources=sources,
                    priority=int(item.get("priority") or idx),
                )
            )
        if len(subquestions) < self.settings.min_subquestions:
            raise ValueError(
                f"Expected at least {self.settings.min_subquestions} subquestions"
            )
        subquestions = subquestions[: self.settings.max_subquestions]
        return ResearchPlan(
            original_query=query,
            subquestions=subquestions,
            max_subquestions=self.settings.max_subquestions,
        )

    async def maybe_reformulate(
        self,
        plan: ResearchPlan,
        results: list[ResearcherResult],
    ) -> ResearchPlan | None:
        """Optionally reformulate insufficient/failed sub-questions once."""
        weak = [
            r
            for r in results
            if r.status in {ResearcherStatus.FAILED, ResearcherStatus.INSUFFICIENT}
        ]
        if not weak:
            return None

        weak_ids = {r.subquestion_id for r in weak}
        targets = [sq for sq in plan.subquestions if sq.id in weak_ids]
        if not targets:
            return None

        with log_step(logger, agent="Orchestrator", message="reformulate"):
            payload: dict[str, Any] = {
                "original_query": plan.original_query,
                "weak_subquestions": [sq.model_dump(mode="json") for sq in targets],
                "errors": [
                    {"subquestion_id": r.subquestion_id, "error": r.error_message}
                    for r in weak
                ],
            }
            system = (
                "Reformulate the weak sub-questions to be clearer and more searchable. "
                "Keep the same ids. Return JSON "
                '{"subquestions":[{"id","question","rationale","assigned_sources","priority"}]}'
            )
            try:
                raw = await self.llm.complete(system, str(payload))
                data = extract_json_object(raw)
                rewritten = {
                    item["id"]: item for item in data.get("subquestions") or []
                }
            except (ValidationError, ValueError, KeyError) as exc:
                logger.warning("Reformulation failed: %s", exc)
                return None

            new_subs: list[SubQuestion] = []
            for sq in plan.subquestions:
                if sq.id in rewritten:
                    item = rewritten[sq.id]
                    sources = [
                        SourceType(s)
                        for s in item.get("assigned_sources") or sq.assigned_sources
                    ]
                    new_subs.append(
                        SubQuestion(
                            id=sq.id,
                            question=item.get("question") or sq.question,
                            rationale=item.get("rationale") or sq.rationale,
                            assigned_sources=sources,
                            priority=int(item.get("priority") or sq.priority),
                        )
                    )
                else:
                    new_subs.append(sq)
            return ResearchPlan(
                original_query=plan.original_query,
                subquestions=new_subs,
                max_subquestions=plan.max_subquestions,
            )
