"""Created: 2026-04-02

Purpose: Tests the constructor-driven memory retrieval node behavior.
"""

from types import SimpleNamespace

from src.nodes import MemoryRetrieveNode
from src.memory.layers import ColdMemoryLayer, HotMemoryLayer, WarmMemoryLayer
from src.memory.retrieval.retriever import LayeredMemoryRetriever
from src.memory.store import MemoryStore
from src.memory.types import EpisodicMemory, SemanticMemory, WorkingMemory
from src.tools.registry import ToolRegistry


class FakeLLM:
    """Returns a fixed JSON retrieval plan."""

    model_name = "fake-llm"

    def __init__(self, output: str) -> None:
        self.output = output

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        del system_prompt, user_prompt
        return self.output


def build_store(tmp_path):
    """Builds a small layered store for retrieval-node tests."""
    return MemoryStore(
        hot_layer=HotMemoryLayer(max_items=8),
        warm_layer=WarmMemoryLayer(tmp_path / "memory.db"),
        cold_layer=ColdMemoryLayer(tmp_path / "cold.jsonl"),
        archive_after_days=1,
        default_scope="agent_local",
        agent_id="mailmind",
    )


def test_memory_retrieve_node_uses_configured_memory_targets(tmp_path) -> None:
    store = build_store(tmp_path)
    SemanticMemory(content={"fact": "prefers research roles at DeepMind"}, agent_id="mailmind").store_warm(store)
    EpisodicMemory(content={"event": "asked about DeepMind"}, agent_id="mailmind").store_hot(store)
    retriever = LayeredMemoryRetriever(store=store)
    working = WorkingMemory(session_id="s1")
    working.set_state(agent_id="mailmind")
    node = MemoryRetrieveNode(
        tool_registry=ToolRegistry(),
        memory_retriever=retriever,
        memories=[SemanticMemory, EpisodicMemory, WorkingMemory],
    )

    result = node.execute({"user_input": "DeepMind", "memory": working, "steps": 0, "confidence": 1.0})

    assert set(result["memory_context"].keys()) == {"semantic", "episodic", "working"}
    assert result["memory_context"]["semantic"]
    assert result["memory_context"]["episodic"]
    assert result["memory_context"]["working"].session_id == "s1"


def test_memory_retrieve_node_can_select_targets_via_llm(tmp_path) -> None:
    store = build_store(tmp_path)
    SemanticMemory(content={"fact": "prefers research roles"}, agent_id="mailmind").store_warm(store)
    retriever = LayeredMemoryRetriever(store=store)
    working = WorkingMemory(session_id="s2")
    working.set_state(agent_id="mailmind")
    node = MemoryRetrieveNode(
        tool_registry=ToolRegistry(),
        llm=FakeLLM(output='{"memory_retrievals":[{"target":"semantic","limit":3},{"target":"working","limit":1}]}'),
        memory_retriever=retriever,
        memories=[SemanticMemory, EpisodicMemory, WorkingMemory],
        system_prompt="Choose retrieval targets.",
        user_prompt="Input: {user_input}\nTargets: {memory_targets}",
    )

    result = node.execute({"user_input": "research", "memory": working, "steps": 0, "confidence": 1.0})

    assert set(result["memory_context"].keys()) == {"semantic", "working"}
    assert result["memory_context"]["semantic"]


def test_memory_retrieve_node_respects_state_memory_targets(tmp_path) -> None:
    store = build_store(tmp_path)
    SemanticMemory(content={"fact": "prefers research roles"}, agent_id="mailmind").store_warm(store)
    retriever = LayeredMemoryRetriever(store=store)
    working = WorkingMemory(session_id="s3")
    working.set_state(agent_id="mailmind")
    node = MemoryRetrieveNode(
        tool_registry=ToolRegistry(),
        memory_retriever=retriever,
        memories=[],
    )

    result = node.execute(
        {
            "user_input": "research",
            "memory": working,
            "steps": 0,
            "confidence": 1.0,
            "memory_targets": [{"type": "semantic", "limit": 2, "enabled": True}],
        }
    )

    assert set(result["memory_context"].keys()) == {"semantic"}
    assert result["memory_context"]["semantic"]


def test_memory_retrieve_node_retries_query_candidates_and_emits_retrieval_events(tmp_path) -> None:
    store = build_store(tmp_path)
    stored = SemanticMemory(
        content={"fact": "user prefers async updates"},
        agent_id="mailmind",
        metadata={"topic": "preference"},
    ).store_warm(store)
    retriever = LayeredMemoryRetriever(store=store)
    working = WorkingMemory(session_id="s4")
    working.set_state(agent_id="mailmind")
    node = MemoryRetrieveNode(
        tool_registry=ToolRegistry(),
        memory_retriever=retriever,
        memories=[],
    )

    result = node.execute(
        {
            "user_input": "find preference",
            "memory": working,
            "steps": 0,
            "confidence": 1.0,
            "memory_targets": [
                {
                    "type": "semantic",
                    "limit": 3,
                    "enabled": True,
                    "query": "something unrelated",
                    "query_candidates": ["async updates"],
                    "metadata": {"topic": "preference"},
                    "stop_on_first_hit": True,
                }
            ],
        }
    )

    matches = result["memory_context"]["semantic"]
    assert [record.id for record in matches] == [stored.id]
    assert len(result["memory_retrievals"]) == 2
    assert result["memory_retrievals"][0]["query"] == "something unrelated"
    assert result["memory_retrievals"][0]["result_count"] == 0
    assert result["memory_retrievals"][1]["query"] == "async updates"
    assert result["memory_retrievals"][1]["result_count"] == 1
