"""Created: 2026-03-30

Purpose: Tests the tool framework behavior.
"""

from pathlib import Path

from pydantic import BaseModel

from src.mailmind.classifiers.rules import RulesBasedClassifier
from src.mailmind.core.models import EmailMessage
from src.mailmind.core.policies import YAMLPolicyProvider
from src.mailmind.storage.repository import DuckDBMessageRepository
from src.tools.base import BaseTool
from src.tools.executor import ToolExecutor
from src.tools.registry import ToolRegistry


class EchoInput(BaseModel):
    """Represents input for echo operations."""
    value: str


class EchoOutput(BaseModel):
    """Represents output for echo operations."""
    echoed: str


class EchoTool(BaseTool[EchoInput, EchoOutput]):
    """Implements the echo tool."""
    name = "echo"
    description = "Echo test tool."
    input_schema = EchoInput
    output_schema = EchoOutput

    def execute(self, input: EchoInput) -> EchoOutput:
        return EchoOutput(echoed=input.value)


def test_tool_registry_and_executor_round_trip(tmp_path: Path) -> None:
    repo = DuckDBMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    registry = ToolRegistry()
    registry.register(EchoTool())
    executor = ToolExecutor(registry=registry, repository=repo)
    result = executor.execute("echo", {"value": "hello"})
    logs = repo.list_tool_logs()
    assert result["status"] == "completed"
    assert result["output"]["echoed"] == "hello"
    assert logs[0].tool_name == "echo"


def test_tool_registry_can_serialize_catalog_as_json() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())

    catalog_json = registry.build_catalog_json()

    assert '"name": "echo"' in catalog_json
    assert '"description": "Echo test tool."' in catalog_json


def test_email_search_filters_by_category_and_sender(tmp_path: Path) -> None:
    repo = DuckDBMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    classifier = RulesBasedClassifier(YAMLPolicyProvider(Path("policies/default_policy.yaml")))
    message = EmailMessage(
        source_id="job-1",
        from_email="talent@deepmind.com",
        subject="Research Scientist role",
        body_text="We are selectively hiring a research scientist for multimodal reasoning.",
        received_at="2026-03-29T08:00:00+00:00",
    )
    repo.save_message(message)
    repo.save_classification(classifier.classify(message))
    bundles = repo.search_messages(category="strong_ml_research_job", sender="deepmind", limit=10)
    assert len(bundles) == 1
    assert bundles[0].classification is not None
    assert bundles[0].classification.category.value == "strong_ml_research_job"
