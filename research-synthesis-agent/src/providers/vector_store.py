"""Embedded Chroma vector store for internal knowledge base."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config import Settings, get_settings
from src.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class KBDocument:
    """Document stored / retrieved from the internal KB."""

    id: str
    title: str
    content: str
    source: str = "internal_kb"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KBHit:
    """Retrieval hit from the vector store."""

    document: KBDocument
    score: float


class VectorStore(ABC):
    """Abstract vector store interface."""

    @abstractmethod
    def upsert(self, documents: list[KBDocument]) -> None:
        """Insert or update documents."""

    @abstractmethod
    def query(self, text: str, top_k: int = 5) -> list[KBHit]:
        """Similarity search."""


class InMemoryVectorStore(VectorStore):
    """Simple keyword-overlap store used as fallback / tests."""

    def __init__(self) -> None:
        self._docs: dict[str, KBDocument] = {}

    def upsert(self, documents: list[KBDocument]) -> None:
        for doc in documents:
            self._docs[doc.id] = doc

    def query(self, text: str, top_k: int = 5) -> list[KBHit]:
        tokens = {t.lower() for t in text.split() if len(t) > 2}
        scored: list[KBHit] = []
        for doc in self._docs.values():
            hay = f"{doc.title} {doc.content}".lower()
            overlap = sum(1 for t in tokens if t in hay)
            score = overlap / max(len(tokens), 1)
            if score > 0:
                scored.append(KBHit(document=doc, score=score))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]


class ChromaVectorStore(VectorStore):
    """ChromaDB embedded persistent vector store."""

    def __init__(self, settings: Settings) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        persist_dir = Path(settings.chroma_persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=settings.kb_collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, documents: list[KBDocument]) -> None:
        if not documents:
            return
        self._collection.upsert(
            ids=[d.id for d in documents],
            documents=[d.content for d in documents],
            metadatas=[
                {
                    "title": d.title,
                    "source": d.source,
                    **{k: str(v) for k, v in d.metadata.items()},
                }
                for d in documents
            ],
        )

    def query(self, text: str, top_k: int = 5) -> list[KBHit]:
        if self._collection.count() == 0:
            return []
        result = self._collection.query(query_texts=[text], n_results=top_k)
        hits: list[KBHit] = []
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        for i, doc_id in enumerate(ids):
            meta = metas[i] or {}
            distance = float(dists[i]) if i < len(dists) else 1.0
            score = max(0.0, 1.0 - distance)
            hits.append(
                KBHit(
                    document=KBDocument(
                        id=doc_id,
                        title=str(meta.get("title") or doc_id),
                        content=docs[i] or "",
                        source=str(meta.get("source") or "internal_kb"),
                        metadata=dict(meta),
                    ),
                    score=score,
                )
            )
        return hits


def load_seed_documents(path: str | Path) -> list[KBDocument]:
    """Load KB seed documents from JSON file."""
    seed_path = Path(path)
    if not seed_path.exists():
        logger.warning("KB seed file missing: %s", seed_path)
        return []
    raw = json.loads(seed_path.read_text(encoding="utf-8"))
    docs: list[KBDocument] = []
    for item in raw:
        docs.append(
            KBDocument(
                id=item["id"],
                title=item["title"],
                content=item["content"],
                source=item.get("source", "internal_kb"),
                metadata=item.get("metadata") or {},
            )
        )
    return docs


def create_vector_store(
    settings: Settings | None = None,
    *,
    use_memory: bool = False,
) -> VectorStore:
    """Create and seed the vector store."""
    cfg = settings or get_settings()
    store: VectorStore
    if use_memory:
        store = InMemoryVectorStore()
    else:
        try:
            store = ChromaVectorStore(cfg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chroma unavailable (%s); using in-memory store", exc)
            store = InMemoryVectorStore()

    docs = load_seed_documents(cfg.kb_seed_path)
    if docs:
        store.upsert(docs)
        logger.info("Seeded vector store with %s documents", len(docs))
    return store
