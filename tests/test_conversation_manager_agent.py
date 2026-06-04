from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

from agents.collection_agent.conversation_manager.BargeInHandler import BargeInHandler
from agents.collection_agent.conversation_manager.ConversationManagerAgent import ConversationManagerAgent
from agents.collection_agent.conversation_manager.ConversationManagerConfig import ConversationManagerConfig
from agents.collection_agent.conversation_manager.MessageDeliveryTracker import MessageDeliveryTracker


class _FakeRuntime:
    def __init__(self, *, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds
        self.calls: list[str] = []

    def run_turn(self, request, event_callback=None):
        self.calls.append(str(request.message))
        if callable(event_callback):
            event_callback({"event": "downstream_started", "payload": {"session_id": request.session_id}})
        time.sleep(self.delay_seconds)
        return {
            "session_id": request.session_id,
            "final_response": f"handled: {request.message}",
            "final_target": "customer",
            "hops": [],
        }

    def start_conversation(self, request):
        return {"turn": {"final_response": "hello", "final_target": "customer"}}

    def reset_conversation(self, request):
        return {"status": "reset", "session_id": request.session_id}

    def session_state(self, session_id):
        return {"session_id": session_id}

    def list_demo_users(self):
        return []

    def conversation_messages(self, session_id, *, limit=120):
        return []

    def latest_trace_for_session(self, session_id):
        return None

    def voice_status(self):
        return {"active": False}

    def stop_voice_call(self, *, force=False):
        return {"active": False}

    def start_voice_call(self, request):
        return {"voice": {"active": True}}


def _config(tmp_path: Path) -> ConversationManagerConfig:
    return ConversationManagerConfig(
        short_wait_seconds=0.02,
        medium_wait_seconds=0.05,
        long_wait_seconds=0.08,
        short_wait_repeat_seconds=None,
        medium_wait_repeat_seconds=0.03,
        long_wait_repeat_seconds=0.03,
        monitor_poll_seconds=0.005,
        filler_enabled=True,
        filler_library_path=(
            Path("/Users/saketm10/Projects/openclaw_agents/agents/collection_agent/conversation_manager/filler_library.json")
        ),
        runtime_dir=tmp_path / "runtime",
    )


def test_instant_response_emits_no_fillers(tmp_path: Path) -> None:
    manager = ConversationManagerAgent(
        config=_config(tmp_path),
        downstream_runtime=_FakeRuntime(delay_seconds=0.005),
    )
    result = manager.run_turn(SimpleNamespace(message="hello", session_id="s1"))
    assert result["final_response"] == "handled: hello"
    assert result["conversation_manager"]["filler_count"] == 0


def test_short_wait_emits_single_short_filler(tmp_path: Path) -> None:
    events: list[dict] = []
    manager = ConversationManagerAgent(
        config=_config(tmp_path),
        downstream_runtime=_FakeRuntime(delay_seconds=0.035),
    )
    result = manager.run_turn(
        SimpleNamespace(message="hello", session_id="s2"),
        event_callback=events.append,
    )
    filler_events = [item for item in events if item.get("event") == "filler_message"]
    assert len(filler_events) == 1
    assert filler_events[0]["payload"]["category"] == "short_wait"
    assert result["conversation_manager"]["filler_categories"] == ["short_wait"]


def test_latest_input_wins_suppresses_stale_response(tmp_path: Path) -> None:
    runtime = _FakeRuntime(delay_seconds=0.08)
    manager = ConversationManagerAgent(config=_config(tmp_path), downstream_runtime=runtime)

    results: list[dict] = []

    def first_turn() -> None:
        results.append(manager.run_turn(SimpleNamespace(message="first", session_id="s3")))

    thread = threading.Thread(target=first_turn, daemon=True)
    thread.start()
    time.sleep(0.02)
    latest = manager.run_turn(SimpleNamespace(message="second", session_id="s3"))
    thread.join()

    stale = results[0]
    assert stale["conversation_manager"]["response_suppressed"] is True
    assert stale["final_response"] == ""
    assert "Latest customer message: second" in latest["conversation_manager"]["downstream_customer_input"]
    assert latest["final_response"].startswith("handled: The customer interrupted while the previous turn was still processing.")
    debug = manager.debug_state("s3")
    assert debug["suppressed_response_count"] >= 1
    assert debug["interrupted_request_id"] is None
    assert debug["interrupted_customer_input"] is None


def test_repeat_request_replays_buffer_without_recomputing(tmp_path: Path) -> None:
    runtime = _FakeRuntime(delay_seconds=0.0)
    manager = ConversationManagerAgent(config=_config(tmp_path), downstream_runtime=runtime)

    first = manager.run_turn(SimpleNamespace(message="tell me", session_id="s4"))
    replay = manager.run_turn(SimpleNamespace(message="Can you repeat that?", session_id="s4"))

    assert first["final_response"] == "handled: tell me"
    assert replay["conversation_manager"]["replayed_from_buffer"] is True
    assert replay["final_response"] == "handled: tell me"
    assert runtime.calls == ["tell me"]


def test_new_business_input_recomputes_collection_agent(tmp_path: Path) -> None:
    runtime = _FakeRuntime(delay_seconds=0.0)
    manager = ConversationManagerAgent(config=_config(tmp_path), downstream_runtime=runtime)

    manager.run_turn(SimpleNamespace(message="tell me", session_id="s5"))
    manager.run_turn(SimpleNamespace(message="Actually I can pay today", session_id="s5"))

    assert runtime.calls == ["tell me", "Actually I can pay today"]


def test_interrupted_input_is_retained_and_forwarded_to_latest_turn(tmp_path: Path) -> None:
    runtime = _FakeRuntime(delay_seconds=0.08)
    manager = ConversationManagerAgent(config=_config(tmp_path), downstream_runtime=runtime)

    def first_turn() -> None:
        manager.run_turn(SimpleNamespace(message="I cannot pay right now", session_id="s5c"))

    thread = threading.Thread(target=first_turn, daemon=True)
    thread.start()
    time.sleep(0.02)
    latest = manager.run_turn(SimpleNamespace(message="Actually I can pay 3000 today", session_id="s5c"))
    thread.join()

    assert "Previous interrupted customer message: I cannot pay right now" in runtime.calls[-1]
    assert "Latest customer message: Actually I can pay 3000 today" in runtime.calls[-1]
    assert latest["conversation_manager"]["interruption_handoff"]["previous_input"] == "I cannot pay right now"
    assert latest["conversation_manager"]["interruption_handoff"]["current_input"] == "Actually I can pay 3000 today"


def test_reset_clears_replay_buffer(tmp_path: Path) -> None:
    runtime = _FakeRuntime(delay_seconds=0.0)
    manager = ConversationManagerAgent(config=_config(tmp_path), downstream_runtime=runtime)

    manager.run_turn(SimpleNamespace(message="first", session_id="s5b"))
    manager.reset_conversation(SimpleNamespace(session_id="s5b"))
    replay = manager.run_turn(SimpleNamespace(message="Can you repeat that?", session_id="s5b"))

    assert replay["conversation_manager"]["replayed_from_buffer"] is False
    assert runtime.calls == ["first", "Can you repeat that?"]


def test_voice_barge_in_updates_delivery_tracker() -> None:
    tracker = MessageDeliveryTracker(estimated_speech_ms_per_character=50.0)
    record = tracker.start_delivery(
        session_id="voice-1",
        message_id="MSG_AGENT_001",
        response_id="RESP_001",
        message_text="the remaining balance can be paid next month.",
        delivery_mode="voice",
    )
    handler = BargeInHandler(delivery_tracker=tracker)
    update = handler.handle_voice_barge_in(
        message_id=record.message_id,
        spoken_ms=900.0,
        spoken_characters=18,
    )
    delivery = update["delivery"]
    assert update["interruption_detected"] is True
    assert delivery["delivery_status"] == "interrupted"
    assert 0 < delivery["spoken_pct"] < 1
    assert delivery["unspoken_text"]


def test_voice_delivery_starts_then_completes(tmp_path: Path) -> None:
    runtime = _FakeRuntime(delay_seconds=0.0)
    manager = ConversationManagerAgent(config=_config(tmp_path), downstream_runtime=runtime)

    result = manager.run_turn(
        SimpleNamespace(message="voice hello", session_id="voice-2"),
        delivery_mode="voice",
    )
    delivery = result["conversation_manager"]["delivery"]
    assert result["conversation_manager"]["delivery_status"] == "started"
    assert result["conversation_manager"]["response_delivered"] is False

    completed = manager.complete_voice_delivery(
        session_id="voice-2",
        message_id=delivery["message_id"],
    )
    assert completed is not None
    assert completed["delivery_status"] == "delivered"


def test_voice_run_turn_then_barge_in_marks_interrupted(tmp_path: Path) -> None:
    runtime = _FakeRuntime(delay_seconds=0.0)
    manager = ConversationManagerAgent(config=_config(tmp_path), downstream_runtime=runtime)

    result = manager.run_turn(
        SimpleNamespace(message="voice barge", session_id="voice-3"),
        delivery_mode="voice",
    )
    delivery = result["conversation_manager"]["delivery"]
    update = manager.handle_voice_barge_in(
        session_id="voice-3",
        spoken_ms=250.0,
        spoken_characters=5,
    )
    assert update["interruption_detected"] is True
    assert update["delivery"]["delivery_status"] == "interrupted"
    debug = manager.debug_state("voice-3")
    buffered = debug["buffered_responses"]
    assert buffered
    assert buffered[-1]["delivery_status"] == "interrupted"


def test_filler_messages_stop_once_latest_response_arrives(tmp_path: Path) -> None:
    events: list[dict] = []
    manager = ConversationManagerAgent(
        config=_config(tmp_path),
        downstream_runtime=_FakeRuntime(delay_seconds=0.04),
    )
    result = manager.run_turn(SimpleNamespace(message="status", session_id="s6"), event_callback=events.append)
    completed_index = next(i for i, item in enumerate(events) if item.get("event") == "processing_completed")
    later_fillers = [
        item for item in events[completed_index + 1 :] if item.get("event") == "filler_message"
    ]
    assert result["conversation_manager"]["response_delivered"] is True
    assert later_fillers == []
