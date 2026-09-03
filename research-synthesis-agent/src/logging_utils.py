"""Structured JSON logging helpers."""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "agent",
            "duration_ms",
            "token_usage",
            "subquestion_id",
            "status",
            "extra",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger for structured JSON output."""
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)


@contextmanager
def log_step(
    logger: logging.Logger,
    *,
    agent: str,
    message: str,
    **fields: Any,
) -> Iterator[dict[str, Any]]:
    """Context manager that logs start/end with duration_ms."""
    ctx: dict[str, Any] = {"agent": agent, **fields}
    start = time.perf_counter()
    logger.info(message, extra={**ctx, "status": "started"})
    try:
        yield ctx
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            f"{message} completed",
            extra={**ctx, "duration_ms": duration_ms, "status": "completed"},
        )
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            f"{message} failed",
            extra={**ctx, "duration_ms": duration_ms, "status": "failed"},
        )
        raise
