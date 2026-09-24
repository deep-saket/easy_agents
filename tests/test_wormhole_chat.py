"""Tests for routed conversational Missions in the local Control Room."""

from __future__ import annotations

from fastapi.testclient import TestClient

from easy_agents.constellation import ChatTurn, ConversationStore
from easy_agents.constellation.api import create_app


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


def test_wormhole_chat_routes_executes_and_explains_context() -> None:
    model = FakeGemma()
    client = TestClient(create_app(gemma_client=model))

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
    assert "highest-impact" in payload["answer"]
    assert model.calls
    assert model.calls[0][0] == ""


def test_wormhole_chat_retains_bounded_prior_turn_context() -> None:
    model = FakeGemma()
    client = TestClient(create_app(gemma_client=model))

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


def test_wormhole_chat_is_advisory_even_when_message_names_external_actions() -> None:
    client = TestClient(create_app(gemma_client=FakeGemma()))

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
    client = TestClient(create_app(gemma_client=UnreadyGemma()))

    response = client.post(
        "/api/v2/wormhole/chat",
        json={"message": "Help me plan my day"},
    )

    assert response.status_code == 503
    assert "127.0.0.1:8080" in response.json()["detail"]


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
