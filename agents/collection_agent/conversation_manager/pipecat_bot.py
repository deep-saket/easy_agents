"""Pipecat voice-runtime entrypoint for ConversationManagerAgent."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agents.collection_agent.pipecat_bot import _build_runtime, _load_runtime_cfg
from agents.collection_agent.conversation_manager.ConversationManagerAgent import ConversationManagerAgent
from agents.collection_agent.conversation_manager.ConversationManagerConfig import ConversationManagerConfig
from speech.pipecat_stt import build_collection_stt_service
from speech.pipecat_tts import build_collection_tts_service
from src.interfaces import PipecatNotInstalledError, build_runner_bot, build_transport_params, run_pipecat_main


class _VoiceDownstreamRuntime:
    """Minimal runtime adapter so ConversationManagerAgent can treat voice as a normal turn source."""

    def __init__(self, *, orchestrator: Any) -> None:
        self._orchestrator = orchestrator

    def run_turn(self, request: Any, event_callback=None) -> dict[str, Any]:
        del event_callback
        session_id = str(getattr(request, "session_id", "")).strip() or "voice-session"
        message = str(getattr(request, "message", "")).strip()
        response = self._orchestrator.handle_text(session_id=session_id, text=message)
        return {
            "session_id": session_id,
            "final_response": response,
            "final_target": "customer",
            "hops": [],
        }


async def _run_bot(transport: Any, runner_args: Any) -> None:
    """Runs the voice pipeline while routing business logic through the wrapper."""

    from pipecat.frames.frames import TranscriptionFrame, TTSSpeakFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
    downstream_orchestrator, runtime_cfg, _config = _build_runtime()
    manager = ConversationManagerAgent(
        config=ConversationManagerConfig.default(base_dir=Path(__file__).resolve().parent),
        downstream_runtime=_VoiceDownstreamRuntime(orchestrator=downstream_orchestrator),
    )

    class ManagedTurnProcessor(FrameProcessor):
        """Consumes transcriptions, supports barge-in, and speaks managed responses."""

        def __init__(self, *, default_session_id: str) -> None:
            super().__init__()
            self._default_session_id = default_session_id
            self._active_turn_token = 0
            self._active_speech: dict[str, Any] | None = None
            self._speech_completion_task: asyncio.Task[Any] | None = None

        async def process_frame(self, frame: Any, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)

            if isinstance(frame, TranscriptionFrame):
                finalized = bool(getattr(frame, "finalized", True))
                utterance = str(getattr(frame, "text", "")).strip()
                session_id = str(getattr(frame, "user_id", "") or self._default_session_id)

                if not finalized:
                    if utterance and self._active_speech is not None:
                        await self._interrupt_active_delivery(session_id=session_id)
                    return

                if not utterance:
                    return
                if self._active_speech is not None:
                    await self._interrupt_active_delivery(session_id=session_id)
                self._start_managed_turn(session_id=session_id, utterance=utterance)
                return

            await self.push_frame(frame, direction)

        def _start_managed_turn(self, *, session_id: str, utterance: str) -> None:
            self._active_turn_token += 1
            turn_token = self._active_turn_token
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

            def publish(event: dict[str, Any]) -> None:
                loop.call_soon_threadsafe(queue.put_nowait, event)

            def worker() -> None:
                try:
                    result = manager.run_turn(
                        SimpleNamespace(
                            message=utterance,
                            session_id=session_id,
                            sender="customer",
                            soft_cap=10,
                            hard_cap=50,
                            timeout_seconds=20.0,
                        ),
                        event_callback=publish,
                        delivery_mode="voice",
                    )
                    loop.call_soon_threadsafe(queue.put_nowait, {"event": "turn_complete", "payload": result})
                except BaseException as exc:  # pragma: no cover - voice runtime failure path
                    loop.call_soon_threadsafe(queue.put_nowait, {"event": "turn_error", "payload": {"error": str(exc)}})
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            threading.Thread(target=worker, daemon=True).start()
            asyncio.create_task(self._consume_turn_events(session_id=session_id, turn_token=turn_token, queue=queue))

        async def _consume_turn_events(
            self,
            *,
            session_id: str,
            turn_token: int,
            queue: asyncio.Queue[dict[str, Any] | None],
        ) -> None:
            while True:
                item = await queue.get()
                if item is None:
                    return
                event_name = str(item.get("event", "")).strip()
                payload = item.get("payload", {}) if isinstance(item.get("payload"), dict) else {}
                if turn_token != self._active_turn_token:
                    continue
                if event_name == "filler_message":
                    filler_text = str(payload.get("text", "")).strip()
                    if filler_text:
                        await self._speak_text(
                            session_id=session_id,
                            text=filler_text,
                            kind="filler",
                            delivery=None,
                        )
                elif event_name == "turn_complete":
                    manager_meta = payload.get("conversation_manager", {}) if isinstance(payload, dict) else {}
                    if manager_meta.get("response_suppressed"):
                        continue
                    response_text = str((payload or {}).get("final_response", "")).strip()
                    delivery = manager_meta.get("delivery") if isinstance(manager_meta.get("delivery"), dict) else None
                    if response_text:
                        await self._speak_text(
                            session_id=session_id,
                            text=response_text,
                            kind="business",
                            delivery=delivery,
                        )
                elif event_name == "turn_error":
                    error_text = str(payload.get("error", "")).strip()
                    if error_text:
                        await self._speak_text(
                            session_id=session_id,
                            text=f"Error: {error_text}",
                            kind="error",
                            delivery=None,
                        )

        async def _speak_text(
            self,
            *,
            session_id: str,
            text: str,
            kind: str,
            delivery: dict[str, Any] | None,
        ) -> None:
            if not text:
                return
            self._clear_speech_completion_task()
            estimated_total_ms = float(
                (delivery or {}).get("estimated_total_ms") or max(len(text) * manager.config.estimated_speech_ms_per_character, 1.0)
            )
            self._active_speech = {
                "session_id": session_id,
                "kind": kind,
                "text": text,
                "delivery": delivery,
                "started_monotonic": time.monotonic(),
                "estimated_total_ms": estimated_total_ms,
            }
            await self.push_frame(TTSSpeakFrame(text), FrameDirection.DOWNSTREAM)
            self._speech_completion_task = asyncio.create_task(
                self._finalize_voice_delivery_after_delay(
                    session_id=session_id,
                    delivery=delivery,
                    estimated_total_ms=estimated_total_ms,
                )
            )

        async def _finalize_voice_delivery_after_delay(
            self,
            *,
            session_id: str,
            delivery: dict[str, Any] | None,
            estimated_total_ms: float,
        ) -> None:
            try:
                await asyncio.sleep(max(estimated_total_ms / 1000.0, 0.05))
                if delivery and isinstance(delivery.get("message_id"), str):
                    manager.complete_voice_delivery(session_id=session_id, message_id=str(delivery["message_id"]))
                self._active_speech = None
            except asyncio.CancelledError:
                raise

        async def _interrupt_active_delivery(self, *, session_id: str) -> None:
            active = self._active_speech
            if active is None:
                return
            self._clear_speech_completion_task()
            delivery = active.get("delivery")
            if isinstance(delivery, dict) and isinstance(delivery.get("message_id"), str):
                elapsed_ms = max((time.monotonic() - float(active.get("started_monotonic", time.monotonic()))) * 1000.0, 0.0)
                estimated_total_ms = max(float(active.get("estimated_total_ms", 1.0)), 1.0)
                total_chars = len(str(active.get("text", "")))
                spoken_characters = min(total_chars, int(total_chars * min(elapsed_ms / estimated_total_ms, 1.0)))
                manager.handle_voice_barge_in(
                    session_id=session_id,
                    spoken_ms=elapsed_ms,
                    spoken_characters=spoken_characters,
                )
            await self._emit_interruption_frame()
            self._active_speech = None

        async def _emit_interruption_frame(self) -> None:
            try:
                from pipecat.frames.frames import StartInterruptionFrame
            except Exception:
                return
            try:
                await self.push_frame(StartInterruptionFrame(), FrameDirection.DOWNSTREAM)
            except Exception:
                return

        def _clear_speech_completion_task(self) -> None:
            task = self._speech_completion_task
            if task is not None and not task.done():
                task.cancel()
            self._speech_completion_task = None

    import os

    stt = build_collection_stt_service(
        config=_config,
        base_dir=Path(__file__).resolve().parents[1],
    )
    tts = build_collection_tts_service(
        config=_config,
        output_sample_rate=runtime_cfg.audio_out_sample_rate,
        base_dir=Path(__file__).resolve().parents[1],
    )

    runner_body = getattr(runner_args, "body", None)
    env_session_id = str(os.getenv("COLLECTION_VOICE_SESSION_ID", "")).strip()
    if isinstance(runner_body, dict):
        session_id = str(runner_body.get("session_id", "")).strip() or env_session_id or "voice-session"
    else:
        session_id = env_session_id or "voice-session"
    greeting_text = (
        str(os.getenv("COLLECTION_VOICE_GREETING", "")).strip()
        or "Hello. This is Alex from the collections team. How can I help you today?"
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            ManagedTurnProcessor(default_session_id=session_id),
            tts,
            transport.output(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=runtime_cfg.audio_in_sample_rate,
            audio_out_sample_rate=runtime_cfg.audio_out_sample_rate,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    try:
        @transport.event_handler("on_client_connected")
        async def _on_client_connected(transport_obj: Any, client: Any) -> None:
            del transport_obj, client
            await task.queue_frame(TTSSpeakFrame(greeting_text))
    except Exception:
        pass

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


runtime_cfg = _load_runtime_cfg()
try:
    bot = build_runner_bot(
        run_bot=_run_bot,
        transport_params=build_transport_params(vad_enabled=runtime_cfg.vad_enabled),
    )
except PipecatNotInstalledError:
    bot = None


if __name__ == "__main__":
    if bot is None:
        bot = build_runner_bot(
            run_bot=_run_bot,
            transport_params=build_transport_params(vad_enabled=runtime_cfg.vad_enabled),
        )
    run_pipecat_main()
