"""Synthesizer agent: merges findings into a cited Markdown report."""

from __future__ import annotations

from collections import defaultdict

from src.config import Settings, get_settings
from src.llm import LLMClient, create_llm_client, extract_json_object
from src.logging_utils import get_logger, log_step
from src.schemas.models import (
    Citation,
    Contradiction,
    FinalReport,
    Finding,
    ReportSection,
    ResearcherResult,
    ResearcherStatus,
    ResearchPlan,
)

logger = get_logger(__name__)

SYNTH_SYSTEM = """You are a research synthesizer. Given structured findings, write a
coherent report. Return ONLY JSON:
{
  "executive_summary": "...",
  "sections": [
    {
      "subquestion_id": "sq-1",
      "title": "...",
      "content": "Markdown with citations like [1], [2]",
      "finding_ids": ["f-..."]
    }
  ],
  "contradictions": [
    {"topic": "...", "finding_ids": ["f-a","f-b"], "description": "..."}
  ],
  "limitations": ["..."]
}

Rules:
- Only cite finding ids that appear in the provided findings.
- Use citation numbers that match the provided citation map ([1], [2], ...).
- Explicitly call out contradictions; never silently average conflicting claims.
- If evidence is thin for a sub-question, note it in limitations.
"""


class Synthesizer:
    """Produces the final cited Markdown report from researcher outputs."""

    def __init__(
        self,
        settings: Settings | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm = llm or create_llm_client(self.settings)

    async def synthesize(
        self,
        query: str,
        plan: ResearchPlan,
        results: list[ResearcherResult],
    ) -> FinalReport:
        """Build FinalReport with numbered citations from real findings only."""
        with log_step(logger, agent="Synthesizer", message="synthesize"):
            findings = self._collect_findings(results)
            citations = self._build_citations(findings)
            citation_map = {c.finding_id: c.number for c in citations}
            limitations = self._limitations_from_results(plan, results)

            if not findings:
                report = FinalReport(
                    query=query,
                    executive_summary=(
                        "No se obtuvo evidencia suficiente de los researchers "
                        "para sintetizar un informe fundamentado."
                    ),
                    sections=[],
                    contradictions=[],
                    citations=[],
                    limitations=limitations
                    or ["Ningún researcher devolvió hallazgos utilizables."],
                )
                report.markdown = self._render_markdown(report)
                return report

            payload = {
                "query": query,
                "plan": plan.model_dump(mode="json"),
                "findings": [f.model_dump(mode="json") for f in findings],
                "citation_map": citation_map,
                "preliminary_limitations": limitations,
            }
            raw = await self.llm.complete(SYNTH_SYSTEM, str(payload))
            data = extract_json_object(raw)

            valid_ids = {f.id for f in findings}
            sections = self._parse_sections(data.get("sections") or [], valid_ids)
            contradictions = self._parse_contradictions(
                data.get("contradictions") or [],
                valid_ids,
            )
            extra_limits = [
                str(x) for x in (data.get("limitations") or []) if str(x).strip()
            ]
            all_limits = list(dict.fromkeys([*limitations, *extra_limits]))

            report = FinalReport(
                query=query,
                executive_summary=str(data.get("executive_summary") or "Sin resumen."),
                sections=sections,
                contradictions=contradictions,
                citations=citations,
                limitations=all_limits,
            )
            report.markdown = self._render_markdown(report)
            self._assert_citations_grounded(report, valid_ids)
            return report

    def _collect_findings(self, results: list[ResearcherResult]) -> list[Finding]:
        findings: list[Finding] = []
        for result in results:
            findings.extend(result.findings)
        return findings

    def _build_citations(self, findings: list[Finding]) -> list[Citation]:
        citations: list[Citation] = []
        for idx, finding in enumerate(findings, start=1):
            citations.append(
                Citation(
                    number=idx,
                    finding_id=finding.id,
                    title=finding.source_title,
                    url=finding.source_url,
                    source_type=finding.source_type,
                )
            )
        return citations

    def _limitations_from_results(
        self,
        plan: ResearchPlan,
        results: list[ResearcherResult],
    ) -> list[str]:
        by_sq: dict[str, list[ResearcherResult]] = defaultdict(list)
        for r in results:
            by_sq[r.subquestion_id].append(r)

        limitations: list[str] = []
        for sq in plan.subquestions:
            sq_results = by_sq.get(sq.id, [])
            if not sq_results:
                limitations.append(
                    f"Subpregunta {sq.id} sin resultados de researchers."
                )
                continue
            if all(
                r.status in {ResearcherStatus.FAILED, ResearcherStatus.INSUFFICIENT}
                for r in sq_results
            ):
                limitations.append(
                    f"Evidencia insuficiente para '{sq.question}' ({sq.id})."
                )
            for r in sq_results:
                if r.status == ResearcherStatus.FAILED and r.error_message:
                    limitations.append(
                        f"Fallo {r.researcher_type.value} en {sq.id}: "
                        f"{r.error_message}"
                    )
        return limitations

    def _parse_sections(
        self,
        items: list[dict],
        valid_ids: set[str],
    ) -> list[ReportSection]:
        sections: list[ReportSection] = []
        for item in items:
            fids = [fid for fid in item.get("finding_ids") or [] if fid in valid_ids]
            sections.append(
                ReportSection(
                    subquestion_id=str(item.get("subquestion_id") or ""),
                    title=str(item.get("title") or "Section"),
                    content=str(item.get("content") or ""),
                    finding_ids=fids,
                )
            )
        return sections

    def _parse_contradictions(
        self,
        items: list[dict],
        valid_ids: set[str],
    ) -> list[Contradiction]:
        contradictions: list[Contradiction] = []
        for item in items:
            fids = [fid for fid in item.get("finding_ids") or [] if fid in valid_ids]
            if len(fids) < 2:
                continue
            contradictions.append(
                Contradiction(
                    topic=str(item.get("topic") or "Conflict"),
                    finding_ids=fids,
                    description=str(item.get("description") or ""),
                )
            )
        return contradictions

    def _assert_citations_grounded(
        self,
        report: FinalReport,
        valid_ids: set[str],
    ) -> None:
        for citation in report.citations:
            if citation.finding_id not in valid_ids:
                raise ValueError(
                    f"Citation references unknown finding_id={citation.finding_id}"
                )

    def _render_markdown(self, report: FinalReport) -> str:
        lines: list[str] = [
            "# Research Report",
            "",
            f"**Query:** {report.query}",
            "",
            "## Executive Summary",
            "",
            report.executive_summary,
            "",
        ]
        for section in report.sections:
            lines.extend([f"## {section.title}", "", section.content, ""])

        if report.contradictions:
            lines.extend(["## Contradictions", ""])
            for c in report.contradictions:
                ids = ", ".join(c.finding_ids)
                lines.append(f"- **{c.topic}**: {c.description} ({ids})")
            lines.append("")

        if report.limitations:
            lines.extend(["## Limitations / Information Gaps", ""])
            for lim in report.limitations:
                lines.append(f"- {lim}")
            lines.append("")

        lines.extend(["## References", ""])
        if not report.citations:
            lines.append("_No references available._")
        else:
            for c in report.citations:
                url = c.url or "n/a"
                lines.append(f"[{c.number}] {c.title} — {c.source_type.value} — {url}")
        lines.append("")
        return "\n".join(lines)
