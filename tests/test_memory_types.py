"""Created: 2026-04-02

Purpose: Tests type-owned memory normalization and retrieval helpers.
"""

from pathlib import Path

from src.memory.layers import ColdMemoryLayer, HotMemoryLayer, WarmMemoryLayer
from src.memory.retrieval.retriever import LayeredMemoryRetriever as MemoryRetriever
from src.memory.store import MemoryStore
from src.memory.types import EpisodicMemory, SemanticMemory, parse_memory_item


def build_store(tmp_path: Path) -> MemoryStore:
    """Builds a small layered memory store for type-focused tests."""
    return MemoryStore(
        hot_layer=HotMemoryLayer(max_items=8),
        warm_layer=WarmMemoryLayer(tmp_path / "memory.db"),
        cold_layer=ColdMemoryLayer(tmp_path / "cold.jsonl"),
        archive_after_days=1,
        default_scope="agent_local",
        agent_id="agent-1",
    )


def test_typed_memory_prepare_for_store_uses_type_defaults() -> None:
    record = EpisodicMemory(content={"event": "tool run"})

    stored = record.prepare_for_store(default_scope="agent_local", agent_id="agent-1")

    assert stored.type == "episodic"
    assert stored.layer == "hot"
    assert stored.scope == "agent_local"
    assert stored.agent_id == "agent-1"


def test_typed_memory_retrieval_filters_pin_the_type() -> None:
    filters = SemanticMemory.retrieval_filters(agent_id="mailmind", scope="global")

    assert filters == {"agent_id": "mailmind", "scope": "global", "type": "semantic"}


def test_parse_memory_item_round_trips_to_concrete_type() -> None:
    parsed = parse_memory_item({"type": "semantic", "layer": "warm", "content": {"fact": "prefers research"}})

    assert isinstance(parsed, SemanticMemory)


def test_typed_memory_can_store_and_search_through_the_type_api(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    stored = SemanticMemory(content={"fact": "likes research labs"}).store_warm(store)

    fetched = SemanticMemory.get(store, stored.id)
    searched = SemanticMemory.search(store, "research", agent_id="agent-1")

    assert isinstance(fetched, SemanticMemory)
    assert fetched is not None
    assert fetched.id == stored.id
    assert searched[0].id == stored.id


def test_typed_memory_can_retrieve_through_layered_retriever(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    retriever = MemoryRetriever(store=store)
    stored = EpisodicMemory(content={"event": "tool execution about DeepMind"}).store_hot(store)

    results = EpisodicMemory.retrieve(retriever, "DeepMind", agent_id="agent-1")

    assert results
    assert results[0].id == stored.id
