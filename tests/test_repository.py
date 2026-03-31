"""Created: 2026-03-30

Purpose: Tests the repository behavior.
"""

from pathlib import Path

from mailmind.core.models import ClassificationResult, EmailMessage, SuggestedAction, Category
from mailmind.storage.repository import SQLiteMessageRepository


def test_repository_round_trip(tmp_path: Path) -> None:
    repo = SQLiteMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    message = EmailMessage(
        source_id="abc",
        from_email="person@example.com",
        subject="Hello",
        body_text="Testing repository",
        received_at="2026-03-29T08:00:00+00:00",
    )
    repo.save_message(message)
    repo.save_classification(
        ClassificationResult(
            message_id=message.id,
            priority_score=0.5,
            category=Category.OTHER,
            confidence=0.6,
            reason_codes=["test"],
            suggested_action=SuggestedAction.MANUAL_REVIEW,
            summary="summary",
        )
    )
    loaded = repo.get_message(message.id)
    bundles = repo.list_messages()
    assert loaded is not None
    assert loaded.subject == "Hello"
    assert len(bundles) == 1
    assert bundles[0].classification is not None

