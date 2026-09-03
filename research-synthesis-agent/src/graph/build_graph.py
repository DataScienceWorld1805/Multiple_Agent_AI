"""LangGraph orchestrator → workers → synthesizer graph."""

from __future__ import annotations

import asyncio
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.agents.orchestrator import Orchestrator
from src.agents.researchers.base import BaseResearcher
from src.agents.researchers.internal_kb_researcher import InternalKBResearcher
from src.agents.researchers.papers_researcher import PapersResearcher
from src.agents.researchers.web_researcher import WebResearcher
from src.agents.synthesizer import Synthesizer
from src.config import Settings, get_settings
from src.llm import LLMClient, create_llm_client
from src.logging_utils import get_logger
from src.providers.arxiv_provider import PapersProvider, create_papers_provider
from src.providers.search_provider import SearchProvider, create_search_provider
from src.providers.vector_store import VectorStore, create_vector_store
from src.schemas.models import (
    GraphState,
    ResearcherResult,
    ResearcherStatus,
    ResearchPlan,
    SourceType,
    SubQuestion,
)

logger = get_logger(__name__)


class ResearchGraphApp:
    """Compiled research-synthesis graph with injectable dependencies."""

    def __init__(
        self,
        settings: Settings | None = None,
        llm: LLMClient | None = None,
        search_provider: SearchProvider | None = None,
        papers_provider: PapersProvider | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm = llm or create_llm_client(self.settings)
        self.search_provider = search_provider or create_search_provider(self.settings)
        self.papers_provider = papers_provider or create_papers_provider(self.settings)
        self.vector_store = vector_store or create_vector_store(self.settings)
        self.orchestrator = Orchestrator(self.settings, self.llm)
        self.synthesizer = Synthesizer(self.settings, self.llm)
        self._researchers: dict[SourceType, BaseResearcher] = {
            SourceType.WEB: WebResearcher(self.settings, self.search_provider),
            SourceType.PAPER: PapersResearcher(self.settings, self.papers_provider),
            SourceType.INTERNAL_KB: InternalKBResearcher(
                self.settings,
                self.vector_store,
            ),
        }
        self.graph = self._build()

    def _build(self) -> Any:
        builder: StateGraph = StateGraph(GraphState)
        builder.add_node("orchestrator", self._orchestrator_node)
        builder.add_node("researchers", self._researchers_node)
        builder.add_node("synthesize", self._synthesize_node)
        builder.add_edge(START, "orchestrator")
        builder.add_edge("orchestrator", "researchers")
        builder.add_edge("researchers", "synthesize")
        builder.add_edge("synthesize", END)
        return builder.compile()

    async def _orchestrator_node(self, state: GraphState) -> dict[str, Any]:
        query = state["query"]
        plan = await self.orchestrator.create_plan(query)
        return {"plan": plan, "errors": [], "retry_count": 0}

    async def _researchers_node(self, state: GraphState) -> dict[str, Any]:
        plan = state.get("plan")
        if plan is None:
            return {
                "results": [],
                "errors": ["Missing research plan"],
            }

        results = await self._run_researchers(plan)
        retry_count = int(state.get("retry_count") or 0)
        errors = list(state.get("errors") or [])

        weak = [
            r
            for r in results
            if r.status in {ResearcherStatus.FAILED, ResearcherStatus.INSUFFICIENT}
        ]
        if weak and retry_count < self.settings.max_retries:
            reformulated = await self.orchestrator.maybe_reformulate(plan, results)
            if reformulated is not None:
                logger.info(
                    "Retrying weak subquestions after reformulation",
                    extra={
                        "agent": "researchers",
                        "extra": {"retry_count": retry_count + 1},
                    },
                )
                retry_results = await self._run_researchers(
                    reformulated,
                    only_ids={r.subquestion_id for r in weak},
                )
                results = self._merge_retry_results(results, retry_results)
                plan = reformulated
                retry_count += 1

        for r in results:
            if r.status == ResearcherStatus.FAILED and r.error_message:
                errors.append(
                    f"{r.researcher_type.value}/{r.subquestion_id}: {r.error_message}"
                )

        return {
            "plan": plan,
            "results": results,
            "errors": errors,
            "retry_count": retry_count,
        }

    async def _run_researchers(
        self,
        plan: ResearchPlan,
        only_ids: set[str] | None = None,
    ) -> list[ResearcherResult]:
        tasks: list[asyncio.Task[ResearcherResult]] = []
        meta: list[tuple[SourceType, SubQuestion]] = []

        for sq in plan.subquestions:
            if only_ids is not None and sq.id not in only_ids:
                continue
            for source in sq.assigned_sources:
                researcher = self._researchers.get(source)
                if researcher is None:
                    continue
                meta.append((source, sq))
                tasks.append(asyncio.create_task(researcher.research(sq)))

        if not tasks:
            return []

        logger.info(
            "Launching parallel researchers",
            extra={
                "agent": "researchers",
                "extra": {
                    "n_tasks": len(tasks),
                    "assignments": [
                        {"source": s.value, "subquestion_id": sq.id} for s, sq in meta
                    ],
                },
            },
        )
        # Fan-out: all workers run concurrently via asyncio.gather.
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[ResearcherResult] = []
        for (source, sq), outcome in zip(meta, gathered, strict=True):
            if isinstance(outcome, Exception):
                results.append(
                    ResearcherResult(
                        researcher_type=source,
                        subquestion_id=sq.id,
                        findings=[],
                        status=ResearcherStatus.FAILED,
                        error_message=str(outcome),
                        duration_ms=0.0,
                    )
                )
            else:
                results.append(outcome)
        return results

    def _merge_retry_results(
        self,
        original: list[ResearcherResult],
        retries: list[ResearcherResult],
    ) -> list[ResearcherResult]:
        """Prefer successful retry results over earlier weak ones."""
        index: dict[tuple[SourceType, str], ResearcherResult] = {
            (r.researcher_type, r.subquestion_id): r for r in original
        }
        for r in retries:
            key = (r.researcher_type, r.subquestion_id)
            prev = index.get(key)
            if prev is None:
                index[key] = r
                continue
            if r.status == ResearcherStatus.SUCCESS or (
                prev.status != ResearcherStatus.SUCCESS
                and len(r.findings) >= len(prev.findings)
            ):
                index[key] = r
        return list(index.values())

    async def _synthesize_node(self, state: GraphState) -> dict[str, Any]:
        plan = state.get("plan")
        results = list(state.get("results") or [])
        query = state["query"]
        if plan is None:
            from src.schemas.models import FinalReport

            report = FinalReport(
                query=query,
                executive_summary="No research plan available.",
                limitations=["Orchestrator did not produce a plan."],
            )
            report.markdown = (
                f"# Research Report\n\n**Query:** {query}\n\n"
                "## Limitations / Information Gaps\n\n"
                "- Orchestrator did not produce a plan.\n"
            )
            return {"report": report}

        report = await self.synthesizer.synthesize(query, plan, results)
        return {"report": report}

    async def arun(self, query: str) -> GraphState:
        """Execute the graph for a user query."""
        final: GraphState = await self.graph.ainvoke(
            {
                "query": query,
                "plan": None,
                "results": [],
                "report": None,
                "errors": [],
                "retry_count": 0,
            }
        )
        return final


def build_graph(
    settings: Settings | None = None,
    **deps: Any,
) -> ResearchGraphApp:
    """Factory used by CLI and tests."""
    return ResearchGraphApp(settings=settings, **deps)
