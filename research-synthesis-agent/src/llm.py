"""LLM client abstraction for orchestrator and synthesizer."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

from src.config import Settings, get_settings
from src.logging_utils import get_logger

logger = get_logger(__name__)


class LLMClient(ABC):
    """Abstract LLM interface."""

    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Return model text completion."""


class FakeLLMClient(LLMClient):
    """Deterministic LLM for tests and offline runs."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[dict[str, str]] = []

    async def complete(self, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        for key, value in self.responses.items():
            if key.lower() in user.lower() or key.lower() in system.lower():
                return value
        system_l = system.lower()
        if "research synthesizer" in system_l or "citation_map" in user.lower():
            return json.dumps(
                {
                    "executive_summary": "Summary of findings across sources.",
                    "sections": [
                        {
                            "subquestion_id": "sq-1",
                            "title": "Technical status",
                            "content": "Evidence indicates progress [1].",
                            "finding_ids": [],
                        }
                    ],
                    "contradictions": [],
                    "limitations": ["Limited academic coverage in fake mode."],
                }
            )
        if "reformulate the weak" in system_l:
            return json.dumps({"subquestions": []})
        if "research orchestrator" in system_l or "decompose" in system_l:
            return json.dumps(
                {
                    "subquestions": [
                        {
                            "id": "sq-1",
                            "question": "What is the current technical status?",
                            "rationale": "Need baseline technical facts",
                            "assigned_sources": ["web", "paper"],
                            "priority": 1,
                        },
                        {
                            "id": "sq-2",
                            "question": "What are commercial and economic barriers?",
                            "rationale": "Need market and deployment view",
                            "assigned_sources": ["web", "paper"],
                            "priority": 2,
                        },
                    ]
                }
            )
        return "Fake LLM response."


class OpenAILLMClient(LLMClient):
    """OpenAI chat completions client."""

    def __init__(self, settings: Settings) -> None:
        from openai import AsyncOpenAI

        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for llm_provider=openai")
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature

    async def complete(self, system: str, user: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content or ""
        return content


class AnthropicLLMClient(LLMClient):
    """Anthropic messages client."""

    def __init__(self, settings: Settings) -> None:
        from anthropic import AsyncAnthropic

        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for llm_provider=anthropic")
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature

    async def complete(self, system: str, user: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            temperature=self._temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts: list[str] = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts)


class GeminiLLMClient(LLMClient):
    """Google Gemini client via the google-genai SDK."""

    _DEFAULT_FALLBACKS = (
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
    )

    def __init__(self, settings: Settings) -> None:
        from google import genai
        from google.genai import types

        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required for llm_provider=gemini")
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature
        self._types = types
        # Primary first, then unique fallbacks (skip duplicates of primary).
        ordered = [self._model, *self._DEFAULT_FALLBACKS]
        seen: set[str] = set()
        self._models: list[str] = []
        for name in ordered:
            if name not in seen:
                seen.add(name)
                self._models.append(name)

    async def complete(self, system: str, user: str) -> str:
        from google.genai import errors as genai_errors
        from tenacity import (
            AsyncRetrying,
            retry_if_exception,
            stop_after_attempt,
            wait_exponential,
        )

        def _transient(exc: BaseException) -> bool:
            if isinstance(exc, (genai_errors.ClientError, genai_errors.ServerError)):
                code = getattr(exc, "code", None)
                if code is None:
                    # Fallback: parse leading status from message, e.g. "503 UNAVAILABLE..."
                    message = str(exc)
                    code = int(message.split(" ", 1)[0]) if message[:3].isdigit() else None
                return code in {429, 503}
            return False

        last_error: BaseException | None = None
        for model in self._models:
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(5),
                    wait=wait_exponential(multiplier=1.5, min=2, max=20),
                    retry=retry_if_exception(_transient),
                    reraise=True,
                ):
                    with attempt:
                        response = await self._client.aio.models.generate_content(
                            model=model,
                            contents=user,
                            config=self._types.GenerateContentConfig(
                                system_instruction=system,
                                temperature=self._temperature,
                            ),
                        )
                        text = (response.text or "").strip()
                        if model != self._model:
                            logger.info(
                                "Gemini fallback model used",
                                extra={
                                    "agent": "llm",
                                    "extra": {"model": model, "primary": self._model},
                                },
                            )
                        return text
            except (genai_errors.ClientError, genai_errors.ServerError) as exc:
                last_error = exc
                if not _transient(exc):
                    raise
                logger.warning(
                    "Gemini model unavailable, trying fallback",
                    extra={
                        "agent": "llm",
                        "extra": {"model": model, "error": str(exc)[:180]},
                    },
                )
                continue

        if last_error is not None:
            raise last_error
        return ""


def create_llm_client(settings: Settings | None = None) -> LLMClient:
    """Factory for LLM clients based on settings."""
    cfg = settings or get_settings()
    provider = cfg.llm_provider.lower()
    if provider == "fake":
        return FakeLLMClient()
    if provider == "anthropic":
        return AnthropicLLMClient(cfg)
    if provider == "openai":
        return OpenAILLMClient(cfg)
    if provider == "gemini":
        return GeminiLLMClient(cfg)
    raise ValueError(f"Unsupported llm_provider: {cfg.llm_provider}")


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract a JSON object from model output, tolerating fences."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)
