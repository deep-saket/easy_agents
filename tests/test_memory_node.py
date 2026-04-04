"""Created: 2026-04-02

Purpose: Tests the generic memory update node for graph workflows.
"""

from types import SimpleNamespace

from src.nodes import MemoryNode
from src.memory.layers import ColdMemoryLayer, HotMemoryLayer, WarmMemoryLayer
from src.memory.store import MemoryStore
from src.memory.types import EpisodicMemory, SemanticMemory, WorkingMemory


def build_store(tmp_path):
    """Builds a small memory store for memory-node tests."""
    return MemoryStore(
        hot_layer=HotMemoryLayer(max_items=8),
        warm_layer=WarmMemoryLayer(tmp_path / "memory.db"),
        cold_layer=ColdMemoryLayer(tmp_path / "cold.jsonl"),
        archive_after_days=1,
        default_scope="agent_local",
        agent_id="agent-1",
    )


def test_memory_node_updates_working_memory_from_turn_state() -> None:
    memory = WorkingMemory(session_id="session-1")
    node = MemoryNode(memories=[memory])

    state = node.execute(
        {
            "user_input": "hello",
            "response": "hi",
            "memory": memory,
            "decision": SimpleNamespace(memory_updates=[{"target": "working", "operation": "set_state", "values": {"topic": "greeting"}}]),
        }
    )

    assert state["memory"].state["topic"] == "greeting"
    assert state["memory"].recent_items == [
        {"role": "user", "content": "hello"},
        {"role": "agent", "content": "hi"},
    ]


def test_memory_node_can_store_typed_long_term_memory(tmp_path) -> None:
    store = build_store(tmp_path)
    node = MemoryNode(memory_store=store, memories=[SemanticMemory])

    state = node.execute(
        {
            "decision": SimpleNamespace(
                memory_updates=[
                    {
                        "target": "semantic",
                        "operation": "store",
                        "layer": "warm",
                        "content": {"fact": "user likes research roles"},
                        "agent_id": "agent-1",
                        "metadata": {"tags": ["preference"]},
                    }
                ]
            )
        }
    )

    stored = state["stored_memories"][0]
    assert isinstance(stored, SemanticMemory)
    matches = SemanticMemory.search(store, "research", agent_id="agent-1")
    assert matches
    assert matches[0].id == stored.id


def test_memory_node_can_blindly_store_episodic_turns(tmp_path) -> None:
    store = build_store(tmp_path)
    node = MemoryNode(memory_store=store, memories=[EpisodicMemory])

    state = node.execute({"user_input": "hello", "response": "hi"})

    stored = state["stored_memories"][0]
    assert stored.type == "episodic"


class FakeLLM:
    """Returns a fixed JSON memory plan."""

    model_name = "fake-llm"

    def __init__(self, output: str) -> None:
        self.output = output

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        del system_prompt, user_prompt
        return self.output


def test_memory_node_can_choose_memory_updates_via_llm(tmp_path) -> None:
    store = build_store(tmp_path)
    memory = WorkingMemory(session_id="session-2")
    node = MemoryNode(
        llm=FakeLLM(
            output='{"memory_updates":[{"target":"semantic","layer":"warm","content":{"summary":"store this"}}]}'
        ),
        memories=[memory, SemanticMemory],
        memory_store=store,
        system_prompt="Choose memory updates.",
        user_prompt="Input: {user_input}\nTargets: {memory_targets}",
    )

    state = node.execute({"user_input": "remember this", "response": "done"})

    assert state["memory"].recent_items[0]["content"] == "remember this"
    assert any(isinstance(item, SemanticMemory) for item in state["stored_memories"])


def test_memory_node_respects_state_memory_targets(tmp_path) -> None:
    store = build_store(tmp_path)
    node = MemoryNode(memory_store=store, memories=[])

    state = node.execute(
        {
            "user_input": "hello",
            "response": "hi",
            "memory_targets": [{"type": "episodic", "layer": "cold", "enabled": True}],
        }
    )

    stored = state["stored_memories"][0]
    assert stored.type == "episodic"
    assert stored.layer == "cold"
