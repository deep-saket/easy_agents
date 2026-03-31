from datetime import datetime, timezone
from pathlib import Path

from mailmind.agent.react_agent import ReActAgent
from mailmind.agents.planner import RuleBasedToolPlanner
from mailmind.classifiers.rules import RulesBasedClassifier
from mailmind.core.models import EmailMessage
from mailmind.core.policies import YAMLPolicyProvider
from mailmind.storage.repository import SQLiteMessageRepository
from tools.email_search import EmailSearchTool
from tools.email_summary import EmailSummaryTool
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry


def test_react_agent_handles_clarification_flow(tmp_path: Path) -> None:
    repo = SQLiteMessageRepository(tmp_path / "mailmind.db")
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
