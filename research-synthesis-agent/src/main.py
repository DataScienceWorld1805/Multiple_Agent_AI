"""CLI entrypoint for the research-synthesis multi-agent system."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from src.config import get_settings
from src.graph.build_graph import build_graph
from src.logging_utils import get_logger, setup_logging


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="research-synthesis-agent",
        description="Multi-agent research and synthesis (orchestrator-worker).",
    )
    parser.add_argument(
        "query",
        nargs="+",
        help="Research question / topic",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Optional path to write the Markdown report",
    )
    return parser.parse_args(argv)


async def run(query: str, output: str | None = None) -> int:
    """Run the research graph and print the Markdown report."""
    settings = get_settings()
    setup_logging(settings.log_level)

    if settings.langsmith_tracing:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        if settings.langchain_api_key:
            os.environ.setdefault("LANGCHAIN_API_KEY", settings.langchain_api_key)
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)

    logger = get_logger("src.main")
    logger.info(
        "Starting research run",
        extra={"agent": "main", "extra": {"query": query}},
    )

    app = build_graph(settings)
    state = await app.arun(query)
    report = state.get("report")
    if report is None:
        print("Error: no report produced", file=sys.stderr)
        return 1

    markdown = report.markdown
    print(markdown)
    if output:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(markdown)
        logger.info(
            "Wrote report",
            extra={"agent": "main", "extra": {"output": output}},
        )
    return 0


def main(argv: list[str] | None = None) -> None:
    """Synchronous CLI wrapper."""
    args = parse_args(argv)
    query = " ".join(args.query)
    raise SystemExit(asyncio.run(run(query, args.output)))


if __name__ == "__main__":
    main()
