"""Internal knowledge-base researcher worker."""

from __future__ import annotations

import time
import uuid

from src.agents.researchers.base import BaseResearcher
from src.config import Settings
from src.providers.vector_store import VectorStore, create_vector_store
from src.schemas.models import (
    Finding,
    ResearcherResult,
    ResearcherStatus,
    SourceType,
    SubQuestion,
)


class InternalKBResearcher(BaseResearcher):
    """Research worker backed by a local vector store."""

    source_type = SourceType.INTERNAL_KB

    def __init__(
        self,
        settings: Settings | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        super().__init__(settings)
        self.vector_store = vector_store or create_vector_store(self.settings)

    async def _research_impl(self, subquestion: SubQuestion) -> ResearcherResult:
        start = time.perf_counter()
        hits = self.vector_store.query(
            subquestion.question,
            top_k=self.settings.kb_top_k,
        )
        findings: list[Finding] = []
        for hit in hits:
            doc = hit.document
            findings.append(
                Finding(
                    id=f"f-kb-{uuid.uuid4().hex[:8]}",
                    subquestion_id=subquestion.id,
                    claim=doc.content[:400],
                    evidence=doc.content,
                    source_title=doc.title,
                    source_url=f"kb://{doc.id}",
                    source_type=SourceType.INTERNAL_KB,
                    confidence=min(max(hit.score, 0.0), 1.0),
                    relevance=min(max(hit.score, 0.0), 1.0),
                    metadata={"doc_id": doc.id, "source": doc.source, **doc.metadata},
                )
            )
        duration_ms = (time.perf_counter() - start) * 1000
        status = ResearcherStatus.SUCCESS if findings else ResearcherStatus.INSUFFICIENT
        return ResearcherResult(
            researcher_type=self.source_type,
            subquestion_id=subquestion.id,
            findings=findings,
            status=status,
            error_message=None if findings else "No KB hits",
            duration_ms=duration_ms,
        )
