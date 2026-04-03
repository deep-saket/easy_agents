"""Created: 2026-04-03

Purpose: Tests real-time JSON trace emission from the shared agent runtime.
"""

from datetime import datetime, timezone
from pathlib import Path

from src.mailmind.agent.graph_agent import MailMindGraphAgent
from src.mailmind.agents.planner import RuleBasedToolPlanner
from src.mailmind.classifiers.rules import RulesBasedClassifier
from src.mailmind.core.models import EmailMessage
from src.mailmind.core.policies import YAMLPolicyProvider
from src.mailmind.storage.repository import DuckDBMessageRepository
from src.tools.executor import ToolExecutor
from src.tools.gmail.email_search import EmailSearchTool
from src.tools.gmail.email_summary import EmailSummaryTool
from src.tools.registry import ToolRegistry


class CaptureTraceSink:
    """Collects real-time trace events in memory for assertions."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event: dict) -> None:
        self.events.append(event)


def test_graph_agent_emits_realtime_json_trace_events(tmp_path: Path) -> None:
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

    registry = ToolRegistry()
    registry.register(EmailSearchTool(repository=repo))
    registry.register(EmailSummaryTool(repository=repo))
    executor = ToolExecutor(registry=registry, repository=repo)
    sink = CaptureTraceSink()
    agent = MailMindGraphAgent(
        planner=RuleBasedToolPlanner(),
        executor=executor,
        repository=repo,
        trace_sink=sink,
    )

    response = agent.run("emails from deepmind", "trace-session")

    assert "Research Scientist role" in response
    event_names = [event["event"] for event in sink.events]
    assert "turn_started" in event_names
    assert "node_started" in event_names
    assert "node_finished" in event_names
    assert "tool_call" in event_names
    assert "turn_finished" in event_names
    assert any(event.get("node_name") == "plan" for event in sink.events if event["event"] == "node_started")
