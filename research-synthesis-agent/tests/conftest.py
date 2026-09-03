"""Pytest fixtures."""

from __future__ import annotations

import os

import pytest
from src.config import Settings
from src.llm import FakeLLMClient
from src.providers.arxiv_provider import FakePapersProvider
from src.providers.search_provider import FakeSearchProvider
from src.providers.vector_store import InMemoryVectorStore, KBDocument


@pytest.fixture
def fake_settings(tmp_path) -> Settings:
    """Settings forced into fully offline/fake mode."""
    os.environ["LLM_PROVIDER"] = "fake"
    os.environ["SEARCH_PROVIDER"] = "fake"
    os.environ["PAPERS_PROVIDER"] = "fake"
    seed = tmp_path / "kb.json"
    seed.write_text(
        (
            '[{"id":"t1","title":"Test Doc",'
            '"content":"Fusion energy pilot notes","source":"internal_kb"}]'
        ),
        encoding="utf-8",
    )
    return Settings(
        llm_provider="fake",
        search_provider="fake",
        papers_provider="fake",
        kb_seed_path=str(seed),
        chroma_persist_dir=str(tmp_path / "chroma"),
        max_retries=0,
    )


@pytest.fixture
def fake_llm() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
def fake_search() -> FakeSearchProvider:
    return FakeSearchProvider()


@pytest.fixture
def fake_papers() -> FakePapersProvider:
    return FakePapersProvider()


@pytest.fixture
def memory_store() -> InMemoryVectorStore:
    store = InMemoryVectorStore()
    store.upsert(
        [
            KBDocument(
                id="kb-1",
                title="Fusion note",
                content="Commercial fusion is not yet grid competitive.",
            )
        ]
    )
    return store
