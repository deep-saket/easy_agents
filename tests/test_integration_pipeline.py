"""Created: 2026-03-30

Purpose: Tests the integration pipeline behavior.
"""

from pathlib import Path

from mailmind.container import AppContainer


def test_integration_pipeline_with_fake_adapters(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MAILMIND_DB_PATH", str(tmp_path / "mailmind.db"))
    monkeypatch.setenv("MAILMIND_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("MAILMIND_GMAIL_SEED_PATH", str(Path("data/seed/demo_messages.json").resolve()))
    monkeypatch.setenv("MAILMIND_POLICY_PATH", str(Path("policies/default_policy.yaml").resolve()))
    monkeypatch.setenv("MAILMIND_NOTIFICATION_DESTINATION", "+911234567890")
    monkeypatch.setenv("MAILMIND_WHATSAPP_ALLOWLIST", "+911234567890")
    container = AppContainer.from_env()
    container.repository.init_db()
    bundles = container.orchestrator.process_messages(container.source.fetch_new_messages())
    approvals = container.repository.list_approvals(pending_only=True)
    drafts = container.repository.list_drafts()
    logs = container.audit_log.read_recent()
    assert len(bundles) == 5
    assert len(approvals) >= 1
    assert len(drafts) >= 1
    assert any(entry["event_type"] == "approval_enqueued" for entry in logs)
