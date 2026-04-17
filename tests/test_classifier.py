"""Created: 2026-04-05

Purpose: Tests MailMind email classification through the existing Gmail tool
surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agents.mailmind.helpers import MailMindEmailClassifier
from src.schemas.domain import EmailMessage
from src.storage.duckdb_store import DuckDBMessageRepository
from src.tools.gmail.email_classifier import EmailClassifierTool


@dataclass(slots=True)
class FakeStructuredLLM:
    """Returns a stable MailMind classifier payload for tests."""

    def structured_generate(self, prompt: str, schema: type, **kwargs: object):
        del prompt, kwargs
        return schema.model_validate(
            {
                "category": "strong_ml_research_job",
                "requires_action": True,
                "action_type": "reply",
                "impact_score": 0.93,
                "priority_score": 0.9,
                "confidence": 0.88,
                "reason": "High-signal research opportunity.",
                "reason_codes": ["research_role"],
                "suggested_action": "notify_and_draft",
                "summary": "Strong ML research job to review.",
            }
        )


def test_mailmind_classifier_tool_classifies_unprocessed_email(tmp_path: Path) -> None:
    repo = DuckDBMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    message = repo.save_message(
        EmailMessage(
            source_id="gmail-1",
            from_email="talent@deepmind.com",
            subject="Research Scientist role",
            body_text="We are hiring for frontier multimodal research.",
            received_at=datetime.now(timezone.utc),
        )
    )
    tool = EmailClassifierTool(
        repository=repo,
        classifier=MailMindEmailClassifier(llm=FakeStructuredLLM()),
    )

    result = tool.execute(tool.input_schema())
    stored = repo.get_latest_classification(message.id)

    assert result.classified_count == 1
    assert result.emails[0].category == "strong_ml_research_job"
    assert stored is not None
    assert stored.requires_action is True
    assert stored.reasoning == "High-signal research opportunity."
