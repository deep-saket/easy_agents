"""Conversation manager wrapper around CollectionAgent-facing runtimes."""

from __future__ import annotations

import inspect
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from agents.collection_agent.conversation_manager.BargeInHandler import BargeInHandler
from agents.collection_agent.conversation_manager.ConversationManagerConfig import ConversationManagerConfig
from agents.collection_agent.conversation_manager.FillerManager import FillerManager
from agents.collection_agent.conversation_manager.InterruptionPolicy import InterruptionPolicy
from agents.collection_agent.conversation_manager.LatencyMonitor import FillerEmission, LatencyMonitor
from agents.collection_agent.conversation_manager.MessageDeliveryTracker import MessageDeliveryTracker
from agents.collection_agent.conversation_manager.ResponseBuffer import BufferedResponse, ResponseBuffer


EventCallback = Callable[[dict[str, Any]], None]
WorkCallable = Callable[[], Any]


@dataclass(slots=True)
class ManagedExecutionResult:
    """Wraps downstream execution result plus conversation-manager metadata."""

    result: Any
    metadata: dict[str, Any]


@dataclass(slots=True)
class _SessionControlState:
    """Tracks latest-input-wins state for one customer session."""

    active_request_id: str | None = None
    active_customer_input: str | None = None
    active_task_status: str = "idle"
    latest_customer_input_id: str | None = None
    superseded_request_ids: list[str] = field(default_factory=list)
    pending_response: dict[str, Any] | None = None
    last_delivered_response_id: str | None = None
    last_delivered_message_id: str | None = None
    active_cancel_event: threading.Event | None = None
    suppressed_response_count: int = 0
    interrupted_request_id: str | None = None
    interrupted_customer_input: str | None = None
    interruption_handoff: dict[str, Any] | None = None
    conversation_closing: bool = False
    conversation_closed: bool = False
    termination_grace_seconds: float = 3.0
    closure_timer: threading.Timer | None = None


class ConversationManagerAgent:
    """Owns fillers, interruptions, and customer-facing delivery continuity."""

    def __init__(
        self,
        *,
        config: ConversationManagerConfig,
        downstream_runtime: Any | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.config = config
        self.downstream_runtime = downstream_runtime
        self._clock = clock or time.monotonic
        library_path = config.filler_library_path
        if library_path is None:
            raise ValueError("ConversationManagerConfig.filler_library_path is required.")
        self._filler_manager = FillerManager(library_path)
        self._log_path = self._ensure_log_dir(config.runtime_dir)
        self._response_buffer = ResponseBuffer()
        self._delivery_tracker = MessageDeliveryTracker(
            estimated_speech_ms_per_character=config.estimated_speech_ms_per_character
        )
        self._barge_in_handler = BargeInHandler(delivery_tracker=self._delivery_tracker)
        self._interruption_policy = InterruptionPolicy()
        self._session_states: dict[str, _SessionControlState] = {}
        self._lock = threading.Lock()
        self._request_counter = 0
        self._customer_input_counter = 0
        self._response_counter = 0
        self._message_counter = 0

    def start_conversation(self, request: Any) -> Any:
        session_id = str(getattr(request, "session_id", "")).strip()
        if session_id:
            self._clear_session_runtime_state(session_id)
        return self.downstream_runtime.start_conversation(request)

    def reset_conversation(self, request: Any) -> Any:
        session_id = str(getattr(request, "session_id", "")).strip()
        if session_id:
            self._clear_session_runtime_state(session_id)
        return self.downstream_runtime.reset_conversation(request)

    def session_state(self, session_id: str) -> Any:
        payload = self.downstream_runtime.session_state(session_id)
        debug_state = self.debug_state(session_id)
        if hasattr(payload, "model_dump"):
            data = payload.model_dump(mode="json")
            data["conversation_manager"] = debug_state
            return type(payload)(**data)
        if isinstance(payload, dict):
            merged = dict(payload)
            merged["conversation_manager"] = debug_state
            return merged
        return payload

    def list_demo_users(self) -> Any:
        return self.downstream_runtime.list_demo_users()

    def conversation_messages(self, session_id: str, *, limit: int = 120) -> Any:
        return self.downstream_runtime.conversation_messages(session_id=session_id, limit=limit)

    def latest_trace_for_session(self, session_id: str) -> Any:
        return self.downstream_runtime.latest_trace_for_session(session_id=session_id)

    def recent_logs(self, session_id: str, *, limit: int = 30) -> list[dict[str, Any]]:
        """Returns recent conversation-manager log entries for a session."""

        safe_limit = max(1, min(int(limit), 200))
        if not self._log_path.exists():
            return []
        try:
            lines = self._log_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []

        matches: list[dict[str, Any]] = []
        for raw in reversed(lines):
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if str(payload.get("conversation_id", "")).strip() != session_id:
                continue
            matches.append(payload)
            if len(matches) >= safe_limit:
                break
        matches.reverse()
        return matches

    def voice_status(self) -> Any:
        return self.downstream_runtime.voice_status()

    def stop_voice_call(self, *, force: bool = False) -> Any:
        return self.downstream_runtime.stop_voice_call(force=force)

    def start_voice_call(self, request: Any) -> Any:
        return self.downstream_runtime.start_voice_call(request)

    def run_turn(
        self,
        request: Any,
        *,
        event_callback: EventCallback | None = None,
        delivery_mode: str = "text",
    ) -> dict[str, Any]:
        session_id = str(getattr(request, "session_id", "")).strip() or "conversation-manager-session"
        customer_input = str(getattr(request, "message", "")).strip()
        with self._lock:
            session = self._session_state_for(session_id)
            if session.conversation_closed:
                return self._closed_turn_payload(session_id=session_id)
            self._cancel_pending_closure_locked(session)
        customer_input_id = self._next_id("MSG")
        request_id = self._next_id("REQ")
        superseded_request_id: str | None = None
        interruption_details: dict[str, Any] | None = None
        cancel_event = threading.Event()
        repeat_request_detected = self.config.replay_on_repeat_request and self._interruption_policy.should_replay(
            customer_input
        )

        if repeat_request_detected:
            replay = self._response_buffer.latest_replayable(session_id)
            if replay is not None:
                payload = self._build_replay_payload(
                    session_id=session_id,
                    request_id=request_id,
                    customer_input_id=customer_input_id,
                    customer_input=customer_input,
                    replay=replay,
                    delivery_mode=delivery_mode,
                )
                self._write_log(payload["conversation_manager"])
                return payload

        interruption_handoff: dict[str, Any] | None = None
        with self._lock:
            session = self._session_state_for(session_id)
            if (
                self.config.interruption_handling_enabled
                and self.config.text_mode_latest_input_wins
                and session.active_task_status == "running"
                and session.active_request_id
            ):
                superseded_request_id = session.active_request_id
                session.superseded_request_ids.append(superseded_request_id)
                previous_input = str(session.active_customer_input or "").strip()
                session.interrupted_request_id = superseded_request_id
                session.interrupted_customer_input = previous_input or None
                interruption_handoff = {
                    "previous_request_id": superseded_request_id,
                    "previous_input": previous_input,
                    "current_input": customer_input,
                }
                session.interruption_handoff = dict(interruption_handoff)
                if session.active_cancel_event is not None:
                    session.active_cancel_event.set()
                interruption_details = self._barge_in_handler.handle_text_supersede(
                    active_request_id=superseded_request_id,
                    new_request_id=request_id,
                )
            session.active_request_id = request_id
            session.active_customer_input = customer_input
            session.active_task_status = "running"
            session.latest_customer_input_id = customer_input_id
            session.pending_response = None
            session.active_cancel_event = cancel_event

        downstream_request = self._build_interruption_aware_request(
            request=request,
            interruption_handoff=interruption_handoff,
        )

        def wrapped_callback(payload: dict[str, Any]) -> None:
            if cancel_event.is_set():
                return
            if callable(event_callback):
                enriched = dict(payload)
                enriched.setdefault("payload", {})
                if isinstance(enriched["payload"], dict):
                    enriched["payload"] = dict(enriched["payload"])
                    enriched["payload"].setdefault("request_id", request_id)
                    enriched["payload"].setdefault("customer_input_id", customer_input_id)
                event_callback(enriched)

        execution = self.execute(
            conversation_id=session_id,
            request_id=request_id,
            customer_input_id=customer_input_id,
            cancel_event=cancel_event,
            event_callback=wrapped_callback,
            work=lambda: self._invoke_downstream_run_turn(downstream_request, wrapped_callback),
        )
        payload = execution.result if isinstance(execution.result, dict) else {}
        response_text = str(payload.get("final_response", "")).strip()
        response_target = str(payload.get("final_target", "customer")).strip().lower() or "customer"
        response_id = self._next_id("RESP")
        message_id = self._next_id("MSG_AGENT")

        with self._lock:
            session = self._session_state_for(session_id)
            is_superseded = request_id in session.superseded_request_ids or session.active_request_id != request_id
            if is_superseded:
                session.pending_response = {
                    "request_id": request_id,
                    "response": response_text,
                    "response_target": response_target,
                }
                session.suppressed_response_count += 1
                if session.active_request_id == request_id:
                    session.active_task_status = "superseded"
                    session.active_cancel_event = None
            else:
                session.active_task_status = "completed"
                session.pending_response = {
                    "request_id": request_id,
                    "response": response_text,
                    "response_target": response_target,
                }
                session.active_cancel_event = None

        conversation_manager = dict(execution.metadata)
        conversation_manager.update(
            {
                "request_id": request_id,
                "customer_input_id": customer_input_id,
                "customer_input": customer_input,
                "active_request_id": self.debug_state(session_id)["active_request_id"],
                "latest_customer_input_id": self.debug_state(session_id)["latest_customer_input_id"],
                "superseded_request_ids": self.debug_state(session_id)["superseded_request_ids"],
                "repeat_request_detected": repeat_request_detected,
                "replayed_from_buffer": False,
                "interruption_detected": interruption_details is not None,
                "interruption_type": None if interruption_details is None else interruption_details["interruption_type"],
                "superseded_request_id": superseded_request_id,
                "response_suppressed": is_superseded,
                "interruption_handoff": interruption_handoff,
                "downstream_customer_input": str(getattr(downstream_request, "message", "")).strip(),
                "conversation_complete": bool(payload.get("conversation_complete", False)),
                "conversation_closing": bool(payload.get("conversation_closing", False)),
                "conversation_closed": bool(payload.get("conversation_closed", False)),
                "terminate_call": bool(payload.get("terminate_call", False)),
                "termination_grace_seconds": float(payload.get("termination_grace_seconds", 0.0) or 0.0),
            }
        )

        if is_superseded and self.config.suppress_stale_responses:
            self._response_buffer.store(
                session_id=session_id,
                request_id=request_id,
                response_id=response_id,
                message_id=message_id,
                response_target=response_target,
                message_text=response_text,
                delivery_status="suppressed",
                suppressed=True,
                conversation_manager=conversation_manager,
            )
            suppressed_payload = dict(payload)
            suppressed_payload["final_response"] = ""
            suppressed_payload["conversation_manager"] = conversation_manager
            self._write_log(conversation_manager)
            return suppressed_payload

        delivery = self._delivery_tracker.start_delivery(
            session_id=session_id,
            message_id=message_id,
            response_id=response_id,
            message_text=response_text,
            delivery_mode=delivery_mode,
        )
        if delivery_mode == "text":
            self._delivery_tracker.complete_delivery(message_id)
        delivery_snapshot = delivery.to_dict()
        self._response_buffer.store(
            session_id=session_id,
            request_id=request_id,
            response_id=response_id,
            message_id=message_id,
            response_target=response_target,
            message_text=response_text,
            delivery_status="delivered" if delivery_mode == "text" else "started",
            suppressed=False,
            conversation_manager=conversation_manager,
            delivery=delivery_snapshot,
        )
        if delivery_mode == "text":
            with self._lock:
                session = self._session_state_for(session_id)
                session.last_delivered_response_id = response_id
                session.last_delivered_message_id = message_id
                session.interrupted_request_id = None
                session.interrupted_customer_input = None
                session.interruption_handoff = None
            conversation_manager.update(
                {
                    "response_delivered": True,
                    "last_delivered_response_id": response_id,
                    "delivery_status": "delivered",
                    "delivery": delivery_snapshot,
                }
            )
        else:
            conversation_manager.update(
                {
                    "response_delivered": False,
                    "last_delivered_response_id": None,
                    "delivery_status": "started",
                    "delivery": delivery_snapshot,
                }
            )

        final_payload = dict(payload)
        final_payload["conversation_manager"] = conversation_manager
        if bool(payload.get("terminate_call", False)):
            grace_seconds = max(
                float(payload.get("termination_grace_seconds", self.config.termination_grace_seconds) or 0.0),
                float(self.config.termination_grace_seconds),
                3.0,
            )
            with self._lock:
                session = self._session_state_for(session_id)
                session.conversation_closing = True
                session.termination_grace_seconds = grace_seconds
            if delivery_mode == "text":
                self._schedule_session_closure(session_id=session_id, grace_seconds=grace_seconds)
        self._write_log(conversation_manager)
        return final_payload

    def run_turn_stream(self, request: Any) -> Any:
        from fastapi.responses import StreamingResponse
        import queue

        sentinel = object()
        events: queue.Queue[object] = queue.Queue()

        def publish(payload: dict[str, Any]) -> None:
            events.put(payload)

        def worker() -> None:
            try:
                result = self.run_turn(request, event_callback=publish)
                publish({"event": "turn_complete", "payload": result})
            except Exception as exc:  # pragma: no cover - stream worker failure path
                publish({"event": "turn_error", "payload": {"error": str(exc)}})
            finally:
                events.put(sentinel)

        threading.Thread(target=worker, daemon=True).start()

        def stream() -> Any:
            yield self._sse("stream_open", {"session_id": getattr(request, "session_id", "")})
            while True:
                item = events.get()
                if item is sentinel:
                    break
                if not isinstance(item, dict):
                    continue
                yield self._sse(str(item.get("event", "message")), item.get("payload", {}))
            yield self._sse("stream_close", {"session_id": getattr(request, "session_id", "")})

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    def execute(
        self,
        *,
        conversation_id: str,
        request_id: str,
        customer_input_id: str,
        work: WorkCallable,
        cancel_event: threading.Event,
        event_callback: EventCallback | None = None,
    ) -> ManagedExecutionResult:
        started_at = datetime.now(timezone.utc)
        started_clock = self._clock()
        done_event = threading.Event()
        result_box: dict[str, Any] = {}
        error_box: dict[str, BaseException] = {}
        filler_messages: list[dict[str, Any]] = []

        def publish(event: str, payload: dict[str, Any]) -> None:
            if cancel_event.is_set():
                return
            if callable(event_callback):
                event_callback({"event": event, "payload": payload})

        def on_emit(emission: FillerEmission) -> None:
            if cancel_event.is_set():
                return
            payload = {
                "conversation_id": conversation_id,
                "request_id": request_id,
                "customer_input_id": customer_input_id,
                "text": emission.text,
                "category": emission.category,
                "elapsed_ms": round(emission.elapsed_seconds * 1000, 3),
                "sequence": emission.sequence,
            }
            filler_messages.append(payload)
            publish("filler_message", payload)

        publish(
            "processing_started",
            {
                "conversation_id": conversation_id,
                "request_id": request_id,
                "customer_input_id": customer_input_id,
                "started_at": started_at.isoformat(),
            },
        )

        monitor = LatencyMonitor(
            config=self.config,
            filler_manager=self._filler_manager,
            clock=self._clock,
        )

        def worker() -> None:
            try:
                result_box["value"] = work()
            except BaseException as exc:  # pragma: no cover - bubbled in caller
                error_box["error"] = exc
            finally:
                done_event.set()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        if self.config.filler_enabled:
            monitor.start(done_event=done_event, cancel_event=cancel_event, on_emit=on_emit)
        thread.join()
        done_event.set()
        monitor.stop()

        finished_at = datetime.now(timezone.utc)
        wait_duration_ms = round((self._clock() - started_clock) * 1000, 3)
        metadata = {
            "conversation_id": conversation_id,
            "request_id": request_id,
            "customer_input_id": customer_input_id,
            "wait_duration_ms": wait_duration_ms,
            "filler_messages_sent": filler_messages,
            "filler_categories": [item["category"] for item in filler_messages],
            "filler_count": len(filler_messages),
            "response_delivery_time_ms": wait_duration_ms,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "active_task_status": "superseded" if cancel_event.is_set() else "completed",
        }
        publish(
            "processing_completed",
            {
                "conversation_id": conversation_id,
                "request_id": request_id,
                "wait_duration_ms": wait_duration_ms,
                "filler_count": len(filler_messages),
            },
        )

        if "error" in error_box:
            raise error_box["error"]
        return ManagedExecutionResult(result=result_box.get("value"), metadata=metadata)

    def debug_state(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._session_state_for(session_id)
            return {
                "active_request_id": session.active_request_id,
                "active_customer_input": session.active_customer_input,
                "active_task_status": session.active_task_status,
                "latest_customer_input_id": session.latest_customer_input_id,
                "superseded_request_ids": list(session.superseded_request_ids),
                "pending_response": dict(session.pending_response) if isinstance(session.pending_response, dict) else None,
                "last_delivered_response_id": session.last_delivered_response_id,
                "suppressed_response_count": session.suppressed_response_count,
                "interrupted_request_id": session.interrupted_request_id,
                "interrupted_customer_input": session.interrupted_customer_input,
                "interruption_handoff": (
                    dict(session.interruption_handoff) if isinstance(session.interruption_handoff, dict) else None
                ),
                "conversation_closing": session.conversation_closing,
                "conversation_closed": session.conversation_closed,
                "termination_grace_seconds": session.termination_grace_seconds,
                "buffered_responses": self._response_buffer.all_for_session(session_id),
            }

    def handle_voice_barge_in(
        self,
        *,
        session_id: str,
        spoken_ms: float,
        spoken_characters: int,
    ) -> dict[str, Any]:
        latest = self._delivery_tracker.latest_for_session(session_id)
        if latest is None:
            return {
                "interruption_detected": False,
                "interruption_type": "user_barge_in",
                "delivery": None,
            }
        payload = self._barge_in_handler.handle_voice_barge_in(
            message_id=latest.message_id,
            spoken_ms=spoken_ms,
            spoken_characters=spoken_characters,
        )
        delivery = payload.get("delivery")
        if isinstance(delivery, dict):
            self._response_buffer.update_delivery(
                session_id=session_id,
                message_id=latest.message_id,
                delivery_status=str(delivery.get("delivery_status", "interrupted")),
                delivery=delivery,
            )
        return payload

    def complete_voice_delivery(self, *, session_id: str, message_id: str) -> dict[str, Any] | None:
        record = self._delivery_tracker.complete_delivery(message_id)
        if record is None:
            return None
        snapshot = record.to_dict()
        self._response_buffer.update_delivery(
            session_id=session_id,
            message_id=message_id,
            delivery_status="delivered",
            delivery=snapshot,
        )
        with self._lock:
            session = self._session_state_for(session_id)
            session.last_delivered_response_id = record.response_id
            session.last_delivered_message_id = record.message_id
        return snapshot

    def finalize_conversation(self, session_id: str) -> None:
        self._finalize_session_closure(session_id=session_id)

    def _build_replay_payload(
        self,
        *,
        session_id: str,
        request_id: str,
        customer_input_id: str,
        customer_input: str,
        replay: BufferedResponse,
        delivery_mode: str,
    ) -> dict[str, Any]:
        delivery = replay.delivery or {}
        if self.config.repeat_strategy == "unspoken_only":
            response_text = str(delivery.get("unspoken_text", "")).strip() or replay.message_text
        else:
            response_text = replay.message_text
        response_id = self._next_id("RESP")
        message_id = self._next_id("MSG_AGENT")
        delivery_record = self._delivery_tracker.start_delivery(
            session_id=session_id,
            message_id=message_id,
            response_id=response_id,
            message_text=response_text,
            delivery_mode=delivery_mode,
        )
        if delivery_mode == "text":
            self._delivery_tracker.complete_delivery(message_id)
        delivery_snapshot = delivery_record.to_dict()
        metadata = {
            "conversation_id": session_id,
            "request_id": request_id,
            "customer_input_id": customer_input_id,
            "customer_input": customer_input,
            "wait_duration_ms": 0.0,
            "filler_messages_sent": [],
            "filler_categories": [],
            "filler_count": 0,
            "response_delivery_time_ms": 0.0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "repeat_request_detected": True,
            "replayed_from_buffer": True,
            "replay_source_response_id": replay.response_id,
            "response_suppressed": False,
            "response_delivered": delivery_mode == "text",
            "delivery_status": "replayed" if delivery_mode == "text" else "started",
            "delivery": delivery_snapshot,
            "active_task_status": "completed",
        }
        self._response_buffer.store(
            session_id=session_id,
            request_id=request_id,
            response_id=response_id,
            message_id=message_id,
            response_target="customer",
            message_text=response_text,
            delivery_status="replayed" if delivery_mode == "text" else "started",
            suppressed=False,
            conversation_manager=metadata,
            delivery=delivery_snapshot,
        )
        with self._lock:
            session = self._session_state_for(session_id)
            session.active_request_id = request_id
            session.active_customer_input = None
            session.active_task_status = "completed"
            session.latest_customer_input_id = customer_input_id
            if delivery_mode == "text":
                session.last_delivered_response_id = response_id
                session.last_delivered_message_id = message_id
            session.active_cancel_event = None
        return {
            "session_id": session_id,
            "final_response": response_text,
            "final_target": "customer",
            "hops": [],
            "conversation_manager": metadata,
        }

    def _invoke_downstream_run_turn(self, request: Any, event_callback: EventCallback | None) -> Any:
        run_turn = self.downstream_runtime.run_turn
        if self._supports_event_callback(run_turn):
            return run_turn(request, event_callback=event_callback)
        return run_turn(request)

    def _session_state_for(self, session_id: str) -> _SessionControlState:
        session = self._session_states.get(session_id)
        if session is None:
            session = _SessionControlState()
            self._session_states[session_id] = session
        return session

    def _clear_session_runtime_state(self, session_id: str) -> None:
        with self._lock:
            session = self._session_states.pop(session_id, None)
            if session is not None:
                self._cancel_pending_closure_locked(session)
        self._response_buffer.clear_session(session_id)
        self._delivery_tracker.clear_session(session_id)

    def _schedule_session_closure(self, *, session_id: str, grace_seconds: float) -> None:
        with self._lock:
            session = self._session_state_for(session_id)
            self._cancel_pending_closure_locked(session)
            session.conversation_closing = True
            session.termination_grace_seconds = max(float(grace_seconds), 3.0)
            timer = threading.Timer(
                session.termination_grace_seconds,
                self._finalize_session_closure,
                kwargs={"session_id": session_id},
            )
            timer.daemon = True
            session.closure_timer = timer
            timer.start()

    @staticmethod
    def _cancel_pending_closure_locked(session: _SessionControlState) -> None:
        timer = session.closure_timer
        if timer is not None:
            timer.cancel()
        session.closure_timer = None
        session.conversation_closing = False

    def _finalize_session_closure(self, *, session_id: str) -> None:
        with self._lock:
            session = self._session_state_for(session_id)
            if not session.conversation_closing or session.conversation_closed:
                return
            session.closure_timer = None
            session.conversation_closing = False
            session.conversation_closed = True
            session.active_task_status = "closed"
        finalize = getattr(self.downstream_runtime, "finalize_conversation", None)
        if callable(finalize):
            finalize(session_id)

    def _closed_turn_payload(self, *, session_id: str) -> dict[str, Any]:
        metadata = {
            "conversation_id": session_id,
            "conversation_complete": True,
            "conversation_closing": False,
            "conversation_closed": True,
            "terminate_call": False,
            "termination_grace_seconds": 0.0,
            "response_suppressed": True,
            "response_delivered": False,
            "active_task_status": "closed",
        }
        return {
            "session_id": session_id,
            "final_response": "",
            "final_target": "customer",
            "conversation_complete": True,
            "conversation_closed": True,
            "hops": [],
            "conversation_manager": metadata,
        }

    @staticmethod
    def _compose_interruption_message(*, previous_input: str, current_input: str) -> str:
        prior = previous_input.strip()
        current = current_input.strip()
        if not prior or not current:
            return current or prior
        return (
            "The customer interrupted while the previous turn was still processing.\n"
            f"Previous interrupted customer message: {prior}\n"
            f"Latest customer message: {current}\n"
            "Use the latest message as authoritative, but keep the interrupted message as immediate context."
        )

    def _build_interruption_aware_request(
        self,
        *,
        request: Any,
        interruption_handoff: dict[str, Any] | None,
    ) -> Any:
        if not interruption_handoff:
            return request
        previous_input = str(interruption_handoff.get("previous_input", "")).strip()
        current_input = str(interruption_handoff.get("current_input", "")).strip()
        merged_message = self._compose_interruption_message(
            previous_input=previous_input,
            current_input=current_input,
        )
        payload = dict(vars(request)) if hasattr(request, "__dict__") else {}
        if not payload:
            payload = {
                "session_id": getattr(request, "session_id", ""),
                "message": getattr(request, "message", ""),
            }
        payload["message"] = merged_message
        payload["original_message"] = current_input
        payload["interruption_handoff"] = dict(interruption_handoff)
        return SimpleNamespace(**payload)

    def _next_id(self, prefix: str) -> str:
        with self._lock:
            if prefix == "REQ":
                self._request_counter += 1
                value = self._request_counter
            elif prefix == "MSG":
                self._customer_input_counter += 1
                value = self._customer_input_counter
            elif prefix == "RESP":
                self._response_counter += 1
                value = self._response_counter
            else:
                self._message_counter += 1
                value = self._message_counter
        return f"{prefix}_{value:06d}"

    @staticmethod
    def _supports_event_callback(fn: Callable[..., Any]) -> bool:
        try:
            parameters = inspect.signature(fn).parameters
        except (TypeError, ValueError):  # pragma: no cover - exotic callables
            return False
        return "event_callback" in parameters

    @staticmethod
    def _ensure_log_dir(runtime_dir: Path | None) -> Path:
        base = runtime_dir or Path.cwd() / "runtime"
        log_dir = base / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / "conversation_manager.jsonl"

    def _write_log(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=True)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.write("\n")

    @staticmethod
    def _sse(event_name: str, payload: dict[str, Any]) -> str:
        return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"
