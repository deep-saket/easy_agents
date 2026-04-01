"""Created: 2026-03-31

Purpose: Tests the react agent behavior.
"""

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from src.memory import ColdMemoryLayer, HotMemoryLayer, MemoryIndexer, MemoryRetriever, MemoryStore, SemanticMemory, WarmMemoryLayer
from src.mailmind.agent.react_agent import ReActAgent
from src.mailmind.agents.planner import RuleBasedToolPlanner
from src.mailmind.classifiers.rules import RulesBasedClassifier
from src.mailmind.core.models import EmailMessage
from src.mailmind.core.policies import YAMLPolicyProvider
from src.mailmind.storage.repository import DuckDBMessageRepository
from src.mailmind.schemas.tools import PlannerDecision
from src.tools.gmail.email_search import EmailSearchTool
from src.tools.gmail.email_summary import EmailSummaryTool
from src.tools.executor import ToolExecutor
from src.tools.registry import ToolRegistry


def test_react_agent_handles_clarification_flow(tmp_path: Path) -> None:
    repo = DuckDBMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    classifier = RulesBasedClassifier(YAMLPolicyProvider(Path("policies/default_policy.yaml")))

    messages = [
        EmailMessage(
            source_id="today-job",
            from_email="talent@deepmind.com",
            subject="Research Scientist role",
            body_text="We are hiring a research scientist for multimodal reasoning.",
            received_at=datetime.now(timezone.utc),
        ),
        EmailMessage(
            source_id="today-event",
            from_email="events@founders.ai",
            subject="Invite-only founder dinner",
            body_text="Invite-only networking dinner for deep-tech founders.",
            received_at=datetime.now(timezone.utc),
        ),
    ]
    for message in messages:
        repo.save_message(message)
        repo.save_classification(classifier.classify(message))

    registry = ToolRegistry()
    registry.register(EmailSearchTool(repository=repo))
    registry.register(EmailSummaryTool(repository=repo))
    executor = ToolExecutor(registry=registry, repository=repo)
    agent = ReActAgent(planner=RuleBasedToolPlanner(), executor=executor, repository=repo)

    first_response = agent.run("what emails today?", "react-session")
    second_response = agent.run("job ones", "react-session")

    assert "Do you want:" in first_response
    assert "Research Scientist role" in second_response


class NoopInput(BaseModel):
    value: str


class NoopOutput(BaseModel):
    value: str


class CapturePlanner:
    def __init__(self) -> None:
        self.last_memory_context = None

    def plan(self, *, user_input: str, memory, observation=None, memory_context=None):
        del user_input, memory, observation
        self.last_memory_context = memory_context
        return PlannerDecision(
            thought="Respond directly for test.",
            respond_directly=True,
            response_text="ok",
            done=True,
        )


def test_react_agent_provides_four_memory_types_to_planner(tmp_path: Path) -> None:
    repo = DuckDBMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    warm_layer = WarmMemoryLayer(tmp_path / "memory.db")
    memory_store = MemoryStore(
        hot_layer=HotMemoryLayer(max_items=8),
        warm_layer=warm_layer,
        cold_layer=ColdMemoryLayer(tmp_path / "cold.jsonl"),
        indexer=MemoryIndexer(warm_layer=warm_layer),
    )
    memory_store.add(
        SemanticMemory(
            layer="warm",
            content={"fact": "User prefers research roles"},
            metadata={"agent": "mailmind"},
        )
    )
    registry = ToolRegistry()
    executor = ToolExecutor(registry=registry, repository=repo)
    planner = CapturePlanner()
    agent = ReActAgent(
        planner=planner,
        executor=executor,
        repository=repo,
        memory_retriever=MemoryRetriever(store=memory_store),
    )

    response = agent.run("research roles", "context-session")

    assert response == "ok"
    assert planner.last_memory_context is not None
    assert set(planner.last_memory_context.keys()) == {"semantic", "episodic", "working", "procedural"}


def test_react_agent_writes_reflection_memory_after_tool_execution(tmp_path: Path) -> None:
    repo = DuckDBMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    classifier = RulesBasedClassifier(YAMLPolicyProvider(Path("policies/default_policy.yaml")))
    message = EmailMessage(
        source_id="today-job",
        from_email="talent@deepmind.com",
        subject="Research Scientist role",
        body_text="We are hiring a research scientist for multimodal reasoning.",
        received_at=datetime.now(timezone.utc),
    )
    repo.save_message(message)
    repo.save_classification(classifier.classify(message))

    warm_layer = WarmMemoryLayer(tmp_path / "memory.db")
    memory_store = MemoryStore(
        hot_layer=HotMemoryLayer(max_items=8),
        warm_layer=warm_layer,
        cold_layer=ColdMemoryLayer(tmp_path / "cold.jsonl"),
        indexer=MemoryIndexer(warm_layer=warm_layer),
    )
    registry = ToolRegistry()
    registry.register(EmailSearchTool(repository=repo))
    executor = ToolExecutor(registry=registry, repository=repo)
    agent = ReActAgent(
        planner=RuleBasedToolPlanner(),
        executor=executor,
        repository=repo,
        memory_store=memory_store,
    )

    response = agent.run("emails from deepmind", "reflect-session")
    reflections = memory_store.search("", filters={"type": "reflection"}, limit=10)

    assert "Research Scientist role" in response
    assert reflections
    assert reflections[0].metadata["source"] == "reflect_node"
