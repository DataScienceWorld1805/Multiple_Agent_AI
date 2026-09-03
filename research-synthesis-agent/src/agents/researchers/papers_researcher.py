"""Academic papers researcher worker."""

from __future__ import annotations

import time
import uuid

from src.agents.researchers.base import BaseResearcher
from src.config import Settings
from src.providers.arxiv_provider import PapersProvider, create_papers_provider
from src.schemas.models import (
    Finding,
    ResearcherResult,
    ResearcherStatus,
    SourceType,
    SubQuestion,
)


class PapersResearcher(BaseResearcher):
    """Research worker backed by an academic PapersProvider."""

    source_type = SourceType.PAPER

    def __init__(
        self,
        settings: Settings | None = None,
        papers_provider: PapersProvider | None = None,
    ) -> None:
        super().__init__(settings)
        self.papers_provider = papers_provider or create_papers_provider(self.settings)

    async def _research_impl(self, subquestion: SubQuestion) -> ResearcherResult:
        start = time.perf_counter()
        hits = await self.papers_provider.search(
            subquestion.question,
            max_results=self.settings.arxiv_max_results,
        )
        findings: list[Finding] = []
        for hit in hits:
            authors = ", ".join(hit.authors[:5]) if hit.authors else "Unknown"
            findings.append(
                Finding(
                    id=f"f-paper-{uuid.uuid4().hex[:8]}",
                    subquestion_id=subquestion.id,
                    claim=hit.abstract[:400],
                    evidence=hit.abstract,
                    source_title=hit.title,
                    source_url=hit.url,
                    source_type=SourceType.PAPER,
                    confidence=0.75,
                    relevance=0.7,
                    metadata={
                        "authors": authors,
                        "published": hit.published,
                        "paper_id": hit.paper_id,
                        **hit.metadata,
                    },
                )
            )
        duration_ms = (time.perf_counter() - start) * 1000
        status = ResearcherStatus.SUCCESS if findings else ResearcherStatus.INSUFFICIENT
        return ResearcherResult(
            researcher_type=self.source_type,
            subquestion_id=subquestion.id,
            findings=findings,
            status=status,
            error_message=None if findings else "No paper results",
            duration_ms=duration_ms,
        )
