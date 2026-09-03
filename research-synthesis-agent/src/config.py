"""Application settings loaded from environment / .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration for the research-synthesis agent."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    llm_provider: str = Field(
        default="openai",
        description="openai | anthropic | gemini | fake",
    )
    llm_model: str = Field(default="gpt-4o-mini")
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    # Search / papers
    tavily_api_key: str | None = None
    search_provider: str = Field(
        default="duckduckgo",
        description="duckduckgo | tavily | fake",
    )
    papers_provider: str = Field(default="arxiv", description="arxiv | fake")

    # Research plan
    max_subquestions: int = Field(default=5, ge=2, le=10)
    min_subquestions: int = Field(default=2, ge=2)
    researcher_timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=2, ge=0)
    min_findings_per_result: int = Field(default=1, ge=0)

    # Vector store
    chroma_persist_dir: str = Field(
        default=str(PROJECT_ROOT / "data" / "chroma"),
    )
    kb_seed_path: str = Field(
        default=str(PROJECT_ROOT / "data" / "kb_documents.json"),
    )
    kb_collection_name: str = Field(default="internal_kb")
    kb_top_k: int = Field(default=5, ge=1)

    # Observability
    log_level: str = Field(default="INFO")
    langsmith_tracing: bool = Field(default=False)
    langchain_api_key: str | None = None
    langchain_project: str = Field(default="research-synthesis-agent")

    # Papers
    arxiv_max_results: int = Field(default=5, ge=1, le=25)
    web_max_results: int = Field(default=5, ge=1, le=20)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
