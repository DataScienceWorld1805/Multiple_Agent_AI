"""Common researcher worker interface."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable

from src.config import Settings, get_settings
from src.logging_utils import get_logger, log_step
from src.schemas.models import (
    ResearcherResult,
    ResearcherStatus,
    SourceType,
    SubQuestion,
)

logger = get_logger(__name__)


class BaseResearcher(ABC):
    """Interchangeable researcher worker with shared I/O contract."""

    source_type: SourceType

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @abstractmethod
    async def _research_impl(self, subquestion: SubQuestion) -> ResearcherResult:
        """Provider-specific research implementation."""

    async def research(self, subquestion: SubQuestion) -> ResearcherResult:
        """Run research with timing, timeout handling, and graceful failure."""
        agent_name = self.__class__.__name__
        start = time.perf_counter()
        with log_step(
            logger,
            agent=agent_name,
            message=f"research {subquestion.id}",
            subquestion_id=subquestion.id,
        ):
            try:
                import asyncio

                result = await asyncio.wait_for(
                    self._research_impl(subquestion),
                    timeout=self.settings.researcher_timeout_seconds,
                )
                if (
                    result.status == ResearcherStatus.SUCCESS
                    and len(result.findings) < self.settings.min_findings_per_result
                ):
                    result.status = ResearcherStatus.INSUFFICIENT
                    result.error_message = (
                        result.error_message
                        or "Insufficient findings returned for sub-question"
                    )
                return result
            except TimeoutError:
                duration_ms = (time.perf_counter() - start) * 1000
                logger.error(
                    "Researcher timeout",
                    extra={
                        "agent": agent_name,
                        "subquestion_id": subquestion.id,
                        "duration_ms": duration_ms,
                        "status": "failed",
                    },
                )
                return ResearcherResult(
                    researcher_type=self.source_type,
                    subquestion_id=subquestion.id,
                    findings=[],
                    status=ResearcherStatus.FAILED,
                    error_message="Researcher timed out",
                    duration_ms=duration_ms,
                )
            except Exception as exc:  # noqa: BLE001
                duration_ms = (time.perf_counter() - start) * 1000
                logger.exception(
                    "Researcher error: %s",
                    exc,
                    extra={
                        "agent": agent_name,
                        "subquestion_id": subquestion.id,
                        "duration_ms": duration_ms,
                        "status": "failed",
                    },
                )
                return ResearcherResult(
                    researcher_type=self.source_type,
                    subquestion_id=subquestion.id,
                    findings=[],
                    status=ResearcherStatus.FAILED,
                    error_message=str(exc),
                    duration_ms=duration_ms,
                )


ResearcherFactory = Callable[[Settings | None], BaseResearcher]
