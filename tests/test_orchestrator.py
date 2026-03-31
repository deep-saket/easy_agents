"""Created: 2026-03-30

Purpose: Tests the orchestrator behavior.
"""

from pathlib import Path

from mailmind.approvals.queue import LocalApprovalQueue
from mailmind.classifiers.rules import RulesBasedClassifier
from mailmind.core.orchestrator import MailOrchestrator
from mailmind.core.policies import YAMLPolicyProvider
from mailmind.drafters.simple import SimpleReplyDrafter
from mailmind.logs.jsonl import JSONLAuditLogStore
from mailmind.notifiers.whatsapp import FakeWhatsAppNotifier
from mailmind.storage.repository import SQLiteMessageRepository
from mailmind.sources.gmail import FakeGmailEmailSource


def test_orchestrator_processes_high_priority_message(tmp_path: Path) -> None:
    repo = SQLiteMessageRepository(tmp_path / "mailmind.db")
    repo.init_db()
    audit = JSONLAuditLogStore(tmp_path / "audit.jsonl")
    policy_provider = YAMLPolicyProvider(Path("policies/default_policy.yaml"))
    orchestrator = MailOrchestrator(
        repository=repo,
        classifier=RulesBasedClassifier(policy_provider),
        drafter=SimpleReplyDrafter(),
        notifier=FakeWhatsAppNotifier(("+911234567890",)),
        approval_queue=LocalApprovalQueue(repo),
        audit_log=audit,
        notification_destination="+911234567890",
    )
    message = FakeGmailEmailSource(Path("data/seed/demo_messages.json")).fetch_new_messages()[0]
    bundle = orchestrator.process_message(message)
    approvals = repo.list_approvals(pending_only=True)
    assert bundle.classification is not None
    assert bundle.draft is not None
    assert len(approvals) == 1
    assert approvals[0].payload["destination"] == "+911234567890"

