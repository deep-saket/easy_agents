"""Created: 2026-04-10

Purpose: Tests reusable vector-retrieval contracts and the memory hybrid adapter.
"""

from __future__ import annotations

from pathlib import Path

from src.memory.index import MemoryIndexer, VectorMemoryIndexBackend
from src.memory.layers import ColdMemoryLayer, HotMemoryLayer, WarmMemoryLayer
from src.memory.retrieval.hybrid_retriever import HybridMemoryRetriever
from src.memory.store import MemoryStore
from src.memory.types import SemanticMemory
from src.retrieval.hash_embedding import HashEmbeddingProvider
from src.retrieval.models import IndexedItem, RetrievalHit
from src.retrieval.vector_backend import VectorRetrievalBackend


class InMemoryVectorBackend(VectorRetrievalBackend):
    """Simple deterministic backend used to test the shared contracts."""

    def __init__(self) -> None:
        self.items: dict[str, IndexedItem] = {}

    def upsert(self, item: IndexedItem) -> None:
        self.items[item.item_id] = item

    def delete(self, item_id: str) -> None:
        self.items.pop(item_id, None)

    def search(self, vector: list[float], filters: dict[str, object] | None = None, limit: int = 20) -> list[RetrievalHit]:
        filters = filters or {}
        hits: list[RetrievalHit] = []
        for item in self.items.values():
            if filters.get("scope") and item.metadata.get("scope") != filters["scope"]:
                continue
            if filters.get("agent_id") and item.metadata.get("agent_id") != filters["agent_id"]:
                continue
            if filters.get("type") and item.metadata.get("type") != filters["type"]:
                continue
            score = sum(left * right for left, right in zip(vector, item.vector, strict=False))
            hits.append(RetrievalHit(item_id=item.item_id, score=score, text=item.text, metadata=item.metadata))
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]

    def rebuild(self, items: list[IndexedItem]) -> None:
        self.items = {item.item_id: item for item in items}


def build_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(
        hot_layer=HotMemoryLayer(max_items=8),
        warm_layer=WarmMemoryLayer(tmp_path / "memory.db"),
        cold_layer=ColdMemoryLayer(tmp_path / "cold.jsonl"),
        archive_after_days=30,
        default_scope="agent_local",
        agent_id="mailmind",
    )


def test_memory_indexer_writes_records_into_generic_vector_backend(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    record = SemanticMemory(content={"fact": "prefers research roles at DeepMind"}).store_warm(store)
    backend = InMemoryVectorBackend()
    indexer = MemoryIndexer(
        embedding_provider=HashEmbeddingProvider(_dimension=32),
        index_backend=VectorMemoryIndexBackend(backend),
    )

    indexable = indexer.index_record(record)

    assert indexable.record_id == record.id
    assert record.id in backend.items
    assert backend.items[record.id].metadata["type"] == "semantic"


def test_hybrid_memory_retriever_merges_keyword_and_vector_hits(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    exact = SemanticMemory(content={"fact": "DeepMind research role"}).store_warm(store)
    semantic = SemanticMemory(content={"fact": "research lab opportunity"}).store_warm(store)
    backend = InMemoryVectorBackend()
    provider = HashEmbeddingProvider(_dimension=32)
    indexer = MemoryIndexer(embedding_provider=provider, index_backend=VectorMemoryIndexBackend(backend))
    indexer.index_records([exact, semantic])
    retriever = HybridMemoryRetriever(
        store=store,
        embedding_provider=provider,
        index_backend=VectorMemoryIndexBackend(backend),
        vector_top_k=5,
    )

    results = retriever.retrieve("DeepMind research", filters={"type": "semantic", "agent_id": "mailmind"}, limit=5)

    assert results
    assert {result.id for result in results} >= {exact.id, semantic.id}
