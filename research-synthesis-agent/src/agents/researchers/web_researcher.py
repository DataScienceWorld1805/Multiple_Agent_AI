"""Web researcher worker."""

from __future__ import annotations

import time
import uuid

from src.agents.researchers.base import BaseResearcher
from src.config import Settings
from src.providers.search_provider import SearchProvider, create_search_provider
from src.schemas.models import (
    Finding,
    ResearcherResult,
    ResearcherStatus,
    SourceType,
    SubQuestion,
)


class WebResearcher(BaseResearcher):
    """Research worker backed by a SearchProvider."""

    source_type = SourceType.WEB

    def __init__(
        self,
        settings: Settings | None = None,
        search_provider: SearchProvider | None = None,
    ) -> None:
        super().__init__(settings)
        self.search_provider = search_provider or create_search_provider(self.settings)

    async def _research_impl(self, subquestion: SubQuestion) -> ResearcherResult:
        start = time.perf_counter()
        hits = await self.search_provider.search(
            subquestion.question,
            max_results=self.settings.web_max_results,
        )
        findings: list[Finding] = []
        for hit in hits:
            relevance = min(max(hit.score, 0.0), 1.0)
            # Drop weak / off-topic hits so references stay query-aligned.
            if relevance < 0.35 and hit.score < 0.5:
                continue
            findings.append(
                Finding(
                    id=f"f-web-{uuid.uuid4().hex[:8]}",
                    subquestion_id=subquestion.id,
                    claim=hit.snippet[:400] or hit.title,
                    evidence=hit.snippet,
                    source_title=hit.title,
                    source_url=hit.url or None,
                    source_type=SourceType.WEB,
                    confidence=relevance,
                    relevance=relevance,
                    metadata=hit.metadata,
                )
            )
        duration_ms = (time.perf_counter() - start) * 1000
        status = ResearcherStatus.SUCCESS if findings else ResearcherStatus.INSUFFICIENT
        return ResearcherResult(
            researcher_type=self.source_type,
            subquestion_id=subquestion.id,
            findings=findings,
            status=status,
            error_message=None if findings else "No web results",
            duration_ms=duration_ms,
        )
