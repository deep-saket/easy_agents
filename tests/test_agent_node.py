"""Created: 2026-04-18

Purpose: Tests nested-agent composition through AgentNode.
"""

from src.memory.types import WorkingMemory
from src.nodes import AgentNode


class EchoAgent:
    """Simple nested agent stub used for node tests."""

    agent_name = "echo-agent"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def run(self, user_input: str, session_id: str | None = None) -> str:
        self.calls.append((user_input, session_id))
        return f"echo:{user_input}"


def test_agent_node_delegates_to_nested_agent() -> None:
    delegate = EchoAgent()
    node = AgentNode(agent=delegate)

    update = node.execute({
        "session_id": "session-1",
        "user_input": "hello",
    })

    assert delegate.calls == [("hello", "session-1::delegate::echo-agent")]
    assert update["observation"]["tool_name"] == "agent:echo-agent"
    assert update["observation"]["output"] == "echo:hello"


def test_agent_node_updates_working_memory_state() -> None:
    delegate = EchoAgent()
    memory = WorkingMemory(session_id="session-2")
    node = AgentNode(agent=delegate)

    node.execute({
        "session_id": "session-2",
        "user_input": "remember delegation",
        "memory": memory,
    })

    assert memory.state["last_delegated_agent"] == "echo-agent"
