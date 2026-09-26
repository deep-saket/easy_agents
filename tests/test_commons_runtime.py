"""Tests for durable, reusable Commons Circle services."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from easy_agents.constellation.api import create_app
from easy_agents.constellation.chat import ConversationStore
from easy_agents.constellation.commons_runtime import (
    ApprovalCreate,
    ApprovalDecision,
    ArtifactCreate,
    CalendarDecision,
    CalendarProposalCreate,
    ClaimVerificationRequest,
    CommonsRuntime,
    KnowledgeSourceCreate,
    ScheduledReviewCreate,
    VaultMemoryCreate,
    VaultPurgeRequest,
)
from easy_agents.constellation.satellite_tools import migrate_legacy_chat_memory


class FakeGemma:
    """Minimal ready completion double for Chat integration tests."""

    model_name = "gemma-4-E4B"
    base_url = "http://127.0.0.1:8080"

    @staticmethod
    def is_ready() -> bool:
        return True

    @staticmethod
    def list_models() -> list[str]:
        return ["gemma-4-E4B"]

    @staticmethod
    def generate(system_prompt: str, user_prompt: str) -> str:
        return "bounded answer"

    @staticmethod
    def generate_json(system_prompt: str, user_prompt: str) -> dict[str, object]:
        """Returns explicit model plans for the two Chat integration requests."""

        del system_prompt
        request = user_prompt.rsplit("Request: ", 1)[-1].split("\nPlan:", 1)[0]
        if request.startswith("Remember"):
            action = "memory_write"
            arguments: dict[str, object] = {
                "content": "my experiment uses sample 42"
            }
        else:
            action = "memory_search"
            arguments = {"query": "sample 42", "limit": 5}
        return {
            "circle_id": "commons",
            "planet_id": "personal_steward",
            "actions": [
                {
                    "action": action,
                    "arguments": arguments,
                    "reason": "The model selected the requested memory operation.",
                }
            ],
            "reasoning_summary": "Model-selected Commons integration plan.",
        }


def test_named_vaults_are_isolated_exportable_and_persistent(tmp_path: Path) -> None:
    path = tmp_path / "commons.db"
    runtime = CommonsRuntime(db_path=path)
    personal = runtime.add_memory(
        "personal", VaultMemoryCreate(content="Mom prefers a Sunday call")
    )
    runtime.add_memory(
        "exploration", VaultMemoryCreate(content="Investigate sodium ion storage")
    )

    assert [item.id for item in runtime.search_memory("personal", "Sunday")] == [
        personal.id
    ]
    assert runtime.search_memory("exploration", "Sunday") == ()
    exported = runtime.export_vault("personal")
    assert exported["vault"]["id"] == "personal"
    assert [item["content"] for item in exported["memories"]] == [
        "Mom prefers a Sunday call"
    ]
    with pytest.raises(ValueError, match="delete personal"):
        runtime.purge_vault("personal", VaultPurgeRequest(confirmation="delete"))
    runtime.close()

    restored = CommonsRuntime(db_path=path)
    assert restored.get_memory("personal", personal.id).content.endswith("Sunday call")
    assert restored.purge_vault(
        "personal", VaultPurgeRequest(confirmation="delete personal")
    ) == 1
    assert restored.search_memory("personal") == ()
    restored.close()


def test_legacy_chat_memory_migration_is_idempotent(tmp_path: Path) -> None:
    legacy_path = tmp_path / "galaxy_memory.duckdb"
    connection = duckdb.connect(str(legacy_path))
    connection.execute(
        """
        CREATE TABLE memory_records (
            id VARCHAR, memory_type VARCHAR, content_text VARCHAR,
            source_type VARCHAR, source_id VARCHAR, tags_json JSON,
            created_at TIMESTAMP, scope VARCHAR, agent_id VARCHAR
        )
        """
    )
    connection.execute(
        """
        INSERT INTO memory_records VALUES (
            'legacy-1', 'semantic', 'legacy fact', 'user', 'chat-1',
            '["wormhole_chat"]', CURRENT_TIMESTAMP, 'agent_local', 'galaxy_chat'
        )
        """
    )
    connection.close()
    runtime = CommonsRuntime()

    assert migrate_legacy_chat_memory(runtime, legacy_path) == 1
    assert migrate_legacy_chat_memory(runtime, legacy_path) == 0
    assert runtime.get_memory("personal", "legacy-1").content == "legacy fact"
    runtime.close()


def test_artifacts_are_immutable_versioned_and_soft_deleted() -> None:
    runtime = CommonsRuntime()
    first = runtime.create_artifact(
        ArtifactCreate(name="Opportunity memo", content="Version one")
    )
    second = runtime.create_artifact(
        ArtifactCreate(
            artifact_id=first.artifact_id,
            name="Opportunity memo",
            content="Version two",
        )
    )

    assert (first.version, second.version) == (1, 2)
    assert first.checksum_sha256 != second.checksum_sha256
    assert runtime.get_artifact(first.artifact_id).content == "Version two"
    assert runtime.delete_artifact(first.artifact_id, version=2) == 1
    assert runtime.get_artifact(first.artifact_id).version == 1
    assert len(runtime.list_artifacts(include_deleted=True)) == 2
    runtime.close()


def test_local_knowledge_preserves_citations_and_labels_lexical_support() -> None:
    runtime = CommonsRuntime()
    source = runtime.add_knowledge_source(
        KnowledgeSourceCreate(
            title="Battery note",
            content="Sodium ion batteries avoid lithium and may reduce material cost.",
            source_uri="local://battery-note",
        )
    )

    hits = runtime.search_knowledge("sodium batteries")
    summary = runtime.summarize_knowledge("sodium batteries")
    assessments = runtime.verify_claims(
        ClaimVerificationRequest(
            claims=("Sodium batteries may reduce material cost",),
            source_ids=(source.id,),
        )
    )

    assert hits[0].source_id == source.id
    assert summary.citations == (source.id,)
    assert f"[{source.id}]" in summary.summary
    assert assessments[0].status == "supported"
    assert assessments[0].citations == (source.id,)
    runtime.close()


def test_reviews_approvals_and_calendar_have_durable_local_state() -> None:
    runtime = CommonsRuntime()
    review = runtime.create_review(
        ScheduledReviewCreate(
            title="Review energy thesis",
            due_at=datetime.now(UTC) - timedelta(minutes=1),
            recurrence_days=7,
        )
    )
    assert runtime.claim_due_reviews()[0].status == "due"
    advanced = runtime.finish_review(review.id, status="completed")
    assert advanced.status == "scheduled"
    assert advanced.due_at == review.due_at + timedelta(days=7)

    approval = runtime.create_approval(
        ApprovalCreate(
            mission_id="mission-local",
            effects=("external_send",),
            rationale="Send a draft after review",
            resume_context={"draft_id": "draft-1"},
        )
    )
    decided = runtime.decide_approval(
        approval.id, ApprovalDecision(decision="approved")
    )
    assert decided.status == "approved"
    assert decided.resume_context == {"draft_id": "draft-1"}

    proposal = runtime.propose_calendar(
        CalendarProposalCreate(
            title="Call Mom",
            starts_at=datetime.now(UTC) + timedelta(hours=1),
            ends_at=datetime.now(UTC) + timedelta(hours=2),
        )
    )
    accepted = runtime.decide_calendar(
        proposal.id, CalendarDecision(decision="approved")
    )
    assert accepted.status == "approved"
    assert runtime.inspect_calendar(include_proposed=False)[0].id == proposal.id
    runtime.close()


def test_commons_api_and_chat_share_the_selected_vault(tmp_path: Path) -> None:
    app = create_app(
        gemma_client=FakeGemma(),
        chat_history=ConversationStore(),
        data_dir=tmp_path,
    )
    with TestClient(app) as client:
        written = client.post(
            "/api/v2/wormhole/chat",
            json={
                "message": "Remember that my experiment uses sample 42",
                "vault_id": "exploration",
            },
        )
        personal = client.get(
            "/api/v2/commons/vaults/personal/memories?query=sample"
        )
        exploration = client.get(
            "/api/v2/commons/vaults/exploration/memories?query=sample"
        )
        recalled = client.post(
            "/api/v2/wormhole/chat",
            json={
                "message": "Recall sample 42",
                "vault_id": "exploration",
            },
        )

        assert written.status_code == 200
        assert personal.json() == []
        assert exploration.json()[0]["content"] == "my experiment uses sample 42"
        assert recalled.status_code == 200
        assert "sample 42" in recalled.json()["answer"]


def test_commons_management_api_exposes_all_local_foundations() -> None:
    with TestClient(create_app(gemma_client=FakeGemma())) as client:
        artifact = client.post(
            "/api/v2/commons/artifacts",
            json={"name": "Memo", "content": "Evidence"},
        )
        source = client.post(
            "/api/v2/commons/knowledge/sources",
            json={"title": "Local source", "content": "Primary evidence text"},
        )
        review = client.post(
            "/api/v2/commons/reviews",
            json={"title": "Review", "due_at": datetime.now(UTC).isoformat()},
        )
        due = client.post("/api/v2/commons/reviews/claim-due")
        calendar = client.post(
            "/api/v2/commons/calendar/proposals",
            json={
                "title": "Focus block",
                "starts_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "ends_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
            },
        )
        approval = client.post(
            "/api/v2/commons/approvals",
            json={
                "mission_id": "mission-api",
                "effects": ["external_send"],
                "rationale": "Review before send",
                "resume_context": {"work_order_id": "order-1"},
            },
        )
        summary = client.get("/api/v2/commons/summary")

        assert artifact.status_code == 200
        assert source.status_code == 200
        assert review.status_code == 200
        assert due.status_code == 200
        assert calendar.status_code == 200
        assert approval.status_code == 200
        assert summary.json()["counts"] == {
            "memories": 0,
            "artifacts": 1,
            "knowledge_sources": 1,
            "scheduled_reviews": 1,
            "pending_approvals": 1,
            "calendar_items": 1,
        }
