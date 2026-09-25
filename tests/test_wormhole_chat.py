"""Tests for routed conversational Missions in the local Control Room."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from easy_agents.constellation import ChatTurn, ConversationStore
from easy_agents.constellation.api import create_app
from easy_agents.observability import EventFilter, ObservabilityPipeline


class FakeGemma:
    """Ready deterministic double for the external Gemma completion service."""

    model_name = "gemma-4-E4B"
    base_url = "http://127.0.0.1:8080"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    @staticmethod
    def is_ready() -> bool:
        """Reports the fake inference backend as ready."""

        return True

    @staticmethod
    def list_models() -> list[str]:
        """Returns the fixed model discovery response."""

        return ["gemma-4-E4B"]

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Records the completion prompt and returns deterministic text."""

        self.calls.append((system_prompt, user_prompt))
        return "Start with the highest-impact item, then review progress this evening."


class UnreadyGemma(FakeGemma):
    """Gemma double used to verify dependency failure behavior."""

    @staticmethod
    def is_ready() -> bool:
        """Reports the fake inference backend as unavailable."""

        return False


class RepetitiveGemma(FakeGemma):
    """Completion double whose output must never reach the final answer."""

    def generate_result(self, system_prompt: str, user_prompt: str) -> SimpleNamespace:
        self.calls.append((system_prompt, user_prompt))
        return SimpleNamespace(
            content="repeat " * 40,
            finish_reason="length",
            prompt_tokens=12,
            completion_tokens=40,
            total_tokens=52,
        )


def test_wormhole_chat_routes_executes_and_explains_context() -> None:
    model = FakeGemma()
    client = TestClient(
        create_app(gemma_client=model, chat_history=ConversationStore())
    )

    response = client.post(
        "/api/v2/wormhole/chat",
        json={"message": "calculate a satellite RF link budget"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["trajectory"]["galaxy_id"] == "personal"
    assert payload["trajectory"]["circle_ids"] == ["satcom"]
    assert payload["trajectory"]["planet_ids"] == ["rf_link_budget_specialist"]
    assert payload["trajectory"]["mission_id"] == payload["mission_id"]
    assert payload["route_context"]["galaxy"]["id"] == "personal"
    assert payload["route_context"]["constellations"][0]["id"] == "personal_operations"
    assert payload["route_context"]["planets"][0]["id"] == "rf_link_budget_specialist"
    assert payload["route_context"]["available_satellites"]
    assert payload["route_context"]["invoked_satellites"] == []
    assert payload["route_context"]["rogue_stars"][0]["id"] == "mac_gemma"
    assert payload["used_model"] == "gemma-4-E4B"
    assert payload["answer_source"] == "model"
    assert payload["generation"]["completed"] is True
    assert payload["generation"]["output_used"] is True
    assert payload["generation"]["quality_status"] == "accepted"
    assert "highest-impact" in payload["answer"]
    assert model.calls
    assert model.calls[0][0] == ""


def test_wormhole_chat_retains_bounded_prior_turn_context() -> None:
    model = FakeGemma()
    client = TestClient(
        create_app(gemma_client=model, chat_history=ConversationStore())
    )

    first = client.post(
        "/api/v2/wormhole/chat",
        json={"message": "Help me plan my day"},
    ).json()
    second = client.post(
        "/api/v2/wormhole/chat",
        json={
            "message": "What should I do next?",
            "conversation_id": first["conversation_id"],
        },
    )

    assert second.status_code == 200
    assert second.json()["conversation_id"] == first["conversation_id"]
    assert second.json()["retained_turns"] == 4
    assert "User: Help me plan my day" in model.calls[1][1]
    assert "Assistant:" in model.calls[1][1]


def test_wormhole_chat_deletes_server_side_conversation() -> None:
    model = FakeGemma()
    client = TestClient(
        create_app(gemma_client=model, chat_history=ConversationStore())
    )
    first = client.post(
        "/api/v2/wormhole/chat",
        json={"message": "Help me plan my day"},
    ).json()

    deleted = client.delete(
        f"/api/v2/wormhole/conversations/{first['conversation_id']}"
    )
    restarted = client.post(
        "/api/v2/wormhole/chat",
        json={
            "message": "Start without the prior context",
            "conversation_id": first["conversation_id"],
        },
    )

    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert restarted.status_code == 200
    assert "Help me plan my day" not in model.calls[1][1]
    assert restarted.json()["retained_turns"] == 2


def test_wormhole_chat_is_advisory_even_when_message_names_external_actions() -> None:
    client = TestClient(
        create_app(gemma_client=FakeGemma(), chat_history=ConversationStore())
    )

    response = client.post(
        "/api/v2/wormhole/chat",
        json={
            "message": (
                "Plan my day so I can call mom and buy groceries, but do not "
                "perform either action."
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert not any("Denied effects" in item for item in response.json()["warnings"])


def test_wormhole_chat_fails_cleanly_when_gemma_is_unavailable() -> None:
    client = TestClient(
        create_app(gemma_client=UnreadyGemma(), chat_history=ConversationStore())
    )

    response = client.post(
        "/api/v2/wormhole/chat",
        json={"message": "Help me plan my day"},
    )

    assert response.status_code == 503
    assert "127.0.0.1:8080" in response.json()["detail"]


def test_wormhole_chat_runs_exact_satellite_when_gemma_is_unavailable() -> None:
    client = TestClient(
        create_app(gemma_client=UnreadyGemma(), chat_history=ConversationStore())
    )

    response = client.post(
        "/api/v2/wormhole/chat",
        json={"message": "Convert 5 miles to km"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["answer_source"] == "satellite"
    assert payload["used_model"] is None
    assert payload["generation"] is None
    assert "8.04672 km" in payload["answer"]


def test_wormhole_chat_falls_back_when_model_output_is_rejected() -> None:
    client = TestClient(
        create_app(gemma_client=RepetitiveGemma(), chat_history=ConversationStore())
    )

    response = client.post(
        "/api/v2/wormhole/chat",
        json={"message": "Help me plan tomorrow"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "planned"
    assert payload["answer_source"] == "fallback"
    assert payload["used_model"] == "gemma-4-E4B"
    assert payload["generation"]["completed"] is True
    assert payload["generation"]["output_used"] is False
    assert payload["generation"]["quality_status"] == "rejected"
    assert "repeat repeat" not in payload["answer"]
    assert "deterministic bounded plan" in payload["answer"]


def test_conversation_store_evicts_old_turns_and_threads() -> None:
    store = ConversationStore(max_conversations=1, max_turns=2)
    store.append(
        "chat-one",
        ChatTurn(role="user", content="first"),
        ChatTurn(role="assistant", content="second"),
        ChatTurn(role="user", content="third"),
    )
    store.append(
        "chat-two",
        ChatTurn(role="user", content="new"),
        ChatTurn(role="assistant", content="answer"),
    )

    assert store.read("chat-one") == ()
    assert [item.content for item in store.read("chat-two")] == ["new", "answer"]


def test_conversation_store_persists_and_resets_sqlite_history(tmp_path: Path) -> None:
    path = tmp_path / "chat.db"
    first = ConversationStore(db_path=path, max_turns=4)
    first.append(
        "chat-persistent",
        ChatTurn(role="user", content="remember this"),
        ChatTurn(role="assistant", content="remembered"),
    )
    first.close()

    restored = ConversationStore(db_path=path, max_turns=4)
    assert [item.content for item in restored.read("chat-persistent")] == [
        "remember this",
        "remembered",
    ]
    restored.clear("chat-persistent")
    assert restored.read("chat-persistent") == ()
    restored.close()


def test_wormhole_chat_executes_and_traces_local_satellite(
    tmp_path: Path,
) -> None:
    operations = ObservabilityPipeline.memory()
    client = TestClient(
        create_app(
            gemma_client=FakeGemma(),
            observability=operations,
            chat_history=ConversationStore(),
            data_dir=tmp_path,
        )
    )

    response = client.post(
        "/api/v2/wormhole/chat",
        json={"message": "Convert 5 miles to km"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["trajectory"]["planet_ids"] == ["personal_steward"]
    assert payload["satellite_invocations"][0]["satellite"]["id"] == "unit_convert"
    assert payload["satellite_invocations"][0]["output"]["converted_value"] == 8.04672
    assert payload["route_context"]["invoked_satellites"][0]["id"] == "unit_convert"
    assert payload["status"] == "completed"
    assert payload["answer_source"] == "satellite"
    assert payload["used_model"] is None
    assert payload["generation"] is None
    assert "8.04672 km" in payload["answer"]
    events = operations.events(
        EventFilter(mission_id=payload["mission_id"], limit=200)
    )
    assert "satellite.started" in {item.event_type for item in events}
    assert "satellite.completed" in {item.event_type for item in events}
    composed = next(item for item in events if item.event_type == "response.composed")
    assert composed.status == "completed"
    assert composed.attributes["answer_source"] == "satellite"
    assert composed.attributes["output_used"] is False
    assert composed.attributes["satellite_count"] == 1
    assert operations.projector.mission(payload["mission_id"])["status"] == "completed"


def test_wormhole_chat_writes_and_retrieves_durable_memory(
    tmp_path: Path,
) -> None:
    first_client = TestClient(
        create_app(
            gemma_client=FakeGemma(),
            chat_history=ConversationStore(),
            data_dir=tmp_path,
        )
    )

    written = first_client.post(
        "/api/v2/wormhole/chat",
        json={"message": "Remember that my grocery day is Saturday"},
    )
    restored_client = TestClient(
        create_app(
            gemma_client=FakeGemma(),
            chat_history=ConversationStore(),
            data_dir=tmp_path,
        )
    )
    recalled = restored_client.post(
        "/api/v2/wormhole/chat",
        json={"message": "What do you remember about grocery day?"},
    )

    assert written.status_code == 200
    assert written.json()["route_context"]["invoked_satellites"][0]["id"] == "memory_write"
    assert recalled.status_code == 200
    assert recalled.json()["route_context"]["invoked_satellites"][0]["id"] == "memory_search"
    assert "grocery day is Saturday" in recalled.json()["answer"]


def test_runtime_readiness_separates_executable_and_disabled_features(
    tmp_path: Path,
) -> None:
    client = TestClient(
        create_app(
            gemma_client=FakeGemma(),
            chat_history=ConversationStore(db_path=tmp_path / "chat.db"),
        )
    )

    response = client.get("/api/v2/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "operational"
    assert payload["planets"]["advisory_executable"] == 70
    assert payload["planets"]["autonomous_effects_enabled"] == 0
    assert payload["satellites"]["locally_executable"] == [
        "calculate",
        "memory_search",
        "memory_write",
        "unit_convert",
    ]
    assert "email_send" in payload["satellites"]["not_enabled_in_chat"]
    assert payload["chat"]["persistent"] is True
    assert payload["commons"] == {
        "status": "partial",
        "summary": {
            "operational": 12,
            "partial": 10,
            "declared": 4,
            "disabled": 4,
        },
        "response_provenance": True,
        "generation_quality_checks": True,
    }


def test_commons_readiness_audits_every_declared_component() -> None:
    client = TestClient(
        create_app(gemma_client=FakeGemma(), chat_history=ConversationStore())
    )

    response = client.get("/api/v2/circles/commons/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["circle_id"] == "commons"
    assert payload["status"] == "partial"
    assert payload["summary"] == {
        "operational": 12,
        "partial": 10,
        "declared": 4,
        "disabled": 4,
    }
    assert len(payload["components"]) == 30
    by_id = {item["id"]: item for item in payload["components"]}
    assert by_id["mission_runtime"]["runtime_status"] == "operational"
    assert by_id["artifact_store"]["runtime_status"] == "declared"
    assert by_id["scheduled_review"]["runtime_status"] == "partial"
    assert by_id["gmail_fetch"]["runtime_status"] == "disabled"
    assert payload["runtime"]["response_provenance"] is True
    assert payload["runtime"]["generation_quality_checks"] is True
    assert payload["runtime"]["autonomous_external_effects"] is False
