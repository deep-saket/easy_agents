"""Created: 2026-04-19

Purpose: Tests iterative memory-search behavior inspired by multi-round retrieval.
"""

from src.memory.layers import ColdMemoryLayer, HotMemoryLayer, WarmMemoryLayer
from src.memory.retrieval.retriever import LayeredMemoryRetriever
from src.memory.store import MemoryStore
from src.memory.types import SemanticMemory
from src.schemas.tool_io import MemorySearchInput
from src.tools.memory_search import MemorySearchTool


def build_store(tmp_path) -> MemoryStore:
    return MemoryStore(
        hot_layer=HotMemoryLayer(max_items=8),
        warm_layer=WarmMemoryLayer(tmp_path / "memory.db"),
        cold_layer=ColdMemoryLayer(tmp_path / "cold.jsonl"),
        archive_after_days=1,
        default_scope="agent_local",
        agent_id="mailmind",
    )


def test_memory_search_tool_uses_query_candidates_until_hit(tmp_path) -> None:
    store = build_store(tmp_path)
    memory = SemanticMemory(content={"fact": "vector clocks preserve event order"}, agent_id="mailmind").store_warm(store)
    tool = MemorySearchTool(retriever=LayeredMemoryRetriever(store=store))

    output = tool.execute(
        MemorySearchInput(
            query="unrelated topic",
            query_candidates=["vector clocks"],
            stop_on_first_hit=True,
            max_queries=2,
            limit=5,
        )
    )

    assert output.total == 1
    assert [item.id for item in output.memories] == [memory.id]
    assert output.selected_query == "vector clocks"
    assert [attempt.query for attempt in output.attempts] == ["unrelated topic", "vector clocks"]
    assert [attempt.result_count for attempt in output.attempts] == [0, 1]


def test_memory_search_tool_can_merge_results_across_queries(tmp_path) -> None:
    store = build_store(tmp_path)
    first = SemanticMemory(content={"fact": "redis uses in-memory data structures"}, agent_id="mailmind").store_warm(store)
    second = SemanticMemory(content={"fact": "postgres supports transactional writes"}, agent_id="mailmind").store_warm(store)
    tool = MemorySearchTool(retriever=LayeredMemoryRetriever(store=store))

    output = tool.execute(
        MemorySearchInput(
            query="redis",
            query_candidates=["postgres"],
            stop_on_first_hit=False,
            max_queries=2,
            limit=5,
        )
    )

    assert output.total == 2
    assert {item.id for item in output.memories} == {first.id, second.id}
    assert len(output.attempts) == 2
