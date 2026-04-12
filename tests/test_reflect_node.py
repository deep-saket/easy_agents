"""Created: 2026-04-12

Purpose: Verifies both the default and loop-aware shared reflection node modes.
"""

from __future__ import annotations

from pathlib import Path

from src.memory.layers import ColdMemoryLayer, HotMemoryLayer, WarmMemoryLayer
from src.memory.store import MemoryStore
from src.memory.types import ReflectionMemory
from src.nodes import ReflectNode


class FakeLLM:
    model_name = "fake-reflect-llm"

    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[tuple[str, str]] = []

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.output


def build_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(
        hot_layer=HotMemoryLayer(max_items=8),
        warm_layer=WarmMemoryLayer(tmp_path / "reflect_memory.db"),
        cold_layer=ColdMemoryLayer(tmp_path / "reflect_memory.jsonl"),
        archive_after_days=30,
        default_scope="agent_local",
        agent_id="platform",
    )


def test_reflect_node_returns_reason_and_logs_memory_by_default(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    node = ReflectNode(memory_store=store, agent_name="platform")

    update = node.execute(
        {
            "decision": type("Decision", (), {"thought": "Use email search."})(),
            "observation": {"tool_name": "email_search", "output": {"total": 2}},
        }
    )

    assert update["reflection_complete"] is True
    assert update["reflection_feedback"]["reason"] == "Reflection completed."
    hits = ReflectionMemory.search(store, "", agent_id="platform")
    assert hits
    assert "email_search" in str(hits[0].metadata.get("tool_name"))


def test_reflect_node_can_emit_loop_feedback_and_memory_updates() -> None:
    llm = FakeLLM('{"reason":"Need one more tool step.","is_complete":false}')
    node = ReflectNode(
        llm=llm,
        system_prompt="Reflect on completeness.",
        merge_feedback_into_observation=True,
        emit_memory_update=True,
    )

    update = node.execute(
        {
            "user_input": "What should I reply?",
            "decision": type("Decision", (), {"thought": "Answer directly."})(),
            "observation": {"tool_name": "email_summary", "output": {"total": 1}},
        }
    )

    assert update["reflection_complete"] is False
    assert update["reflection_feedback"]["reason"] == "Need one more tool step."
    assert update["observation"]["reflection_feedback"]["is_complete"] is False
    assert update["memory_updates"][0]["target"] == "reflection"
    assert "Return JSON" in llm.calls[0][1]
