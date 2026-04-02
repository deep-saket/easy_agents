"""Created: 2026-03-31

Purpose: Tests the memory system behavior.
"""

from pathlib import Path

from pydantic import BaseModel

from src.memory.layers import ColdMemoryLayer, HotMemoryLayer, WarmMemoryLayer
from src.memory.models import MemoryRecord
from src.memory.policies import MemoryPolicy
from src.memory.retrieval.retriever import LayeredMemoryRetriever as MemoryRetriever
from src.memory.store import MemoryStore
from src.memory.types import EpisodicMemory, ErrorMemory, SemanticMemory
from src.mailmind.storage.repository import DuckDBMessageRepository
from src.tools.base import BaseTool
from src.tools.executor import ToolExecutor
from src.tools.memory_write import MemoryWriteTool
from src.tools.registry import ToolRegistry


class FailingInput(BaseModel):
    """Represents input for failing operations."""
    value: str


class FailingOutput(BaseModel):
    """Represents output for failing operations."""
    value: str


class FailingTool(BaseTool[FailingInput, FailingOutput]):
    """Implements the failing tool."""
    name = "failing_tool"
    description = "Always fails."
    input_schema = FailingInput
    output_schema = FailingOutput

    def execute(self, input: FailingInput) -> FailingOutput:
        raise RuntimeError(f"boom: {input.value}")


def build_store(tmp_path: Path) -> MemoryStore:
    warm_layer = WarmMemoryLayer(tmp_path / "memory.db")
    return MemoryStore(
        hot_layer=HotMemoryLayer(max_items=8),
        warm_layer=warm_layer,
        cold_layer=ColdMemoryLayer(tmp_path / "cold.jsonl"),
        archive_after_days=1,
    )


def test_memory_store_and_retriever_promote_cold_items(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    retriever = MemoryRetriever(store=store)

    hot_item = EpisodicMemory(
        layer="hot",
        content={"note": "recent tool execution about DeepMind"},
        metadata={"agent": "mailmind"},
    )
    cold_item = SemanticMemory(
        layer="cold",
        content={"fact": "User prefers research-heavy roles in India"},
        metadata={"agent": "mailmind", "kind": "preference"},
    )

    store.add(hot_item)
    store.add(cold_item)

    hot_results = retriever.retrieve("DeepMind", filters={"metadata": {"agent": "mailmind"}}, limit=5)
    assert hot_results[0].id == hot_item.id

    cold_results = retriever.retrieve("research-heavy roles", filters={"type": "semantic"}, limit=5)
    assert cold_results[0].id == cold_item.id
    assert store.warm_layer.get(cold_item.id) is not None


def test_memory_write_tool_and_executor_policy_capture(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    repo = DuckDBMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    registry = ToolRegistry()
    registry.register(MemoryWriteTool(store=store))
    executor = ToolExecutor(registry=registry, repository=repo, memory_store=store, memory_policy=MemoryPolicy())

    memory_item = MemoryRecord(
        type="semantic",
        layer="warm",
        content={"fact": "User values selective research labs"},
        metadata={"agent": "mailmind"},
    )

    result = executor.execute("memory_write", {"item": memory_item.model_dump(mode="json")})
    assert result["status"] == "completed"
    assert store.get(memory_item.id) is not None

    tool_event_memories = store.search("memory_write", filters={"type": "episodic"}, limit=10)
    assert any(memory.metadata.get("tool_name") == "memory_write" for memory in tool_event_memories)


def test_tool_failures_are_recorded_as_error_memory(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    repo = DuckDBMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    registry = ToolRegistry()
    registry.register(FailingTool())
    executor = ToolExecutor(registry=registry, repository=repo, memory_store=store, memory_policy=MemoryPolicy())

    try:
        executor.execute("failing_tool", {"value": "bad input"})
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected failing_tool to raise RuntimeError")

    error_memories = store.search("boom", filters={"type": "error"}, limit=10)
    assert len(error_memories) == 1
    assert error_memories[0].content.error_type == "tool_failure"
    assert isinstance(error_memories[0], ErrorMemory)
