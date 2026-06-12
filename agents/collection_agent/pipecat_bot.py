"""Pipecat voice-runtime entrypoint for Collection Agent.

Run examples:
  python agents/collection_agent/pipecat_bot.py -t webrtc
  python agents/collection_agent/pipecat_bot.py -t daily
  python agents/collection_agent/pipecat_bot.py -t twilio -x <your-ngrok-domain>
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agents.collection_agent.agent import CollectionAgent
from agents.collection_agent.main import _route_internal_turn, build_llm, load_collection_config
from agents.collection_agent.nodes.plan_proposal_utils import finalize_conversation_memory
from agents.collection_agent.repository import CollectionRepository
from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_memory_helper_agent.agent import CollectionMemoryHelperAgent
from agents.collection_memory_helper_agent.repository import CollectionMemoryRepository
from agents.discount_planning_agent.agent import DiscountPlanningAgent
from speech.pipecat_stt import build_collection_stt_service
from speech.pipecat_tts import build_collection_tts_service
from src.interfaces import PipecatNotInstalledError, PipecatRunnerConfig, build_runner_bot, run_pipecat_main

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yml"


class CollectionVoiceOrchestrator:
    """Bridges Pipecat transcript turns to collection-agent business logic."""

    def __init__(
        self,
        *,
        collection_agent: CollectionAgent,
        discount_agent: DiscountPlanningAgent,
        memory_helper_agent: CollectionMemoryHelperAgent,
        soft_cap: int,
        hard_cap: int,
    ) -> None:
        self._collection_agent = collection_agent
        self._discount_agent = discount_agent
        self._memory_helper_agent = memory_helper_agent
        self._soft_cap = soft_cap
        self._hard_cap = hard_cap

    def handle_text(self, *, session_id: str, text: str) -> str:
        """Runs one user turn through the existing multi-agent collection orchestration."""

        return _route_internal_turn(
            collection_agent=self._collection_agent,
            discount_agent=self._discount_agent,
            memory_helper_agent=self._memory_helper_agent,
            session_id=session_id,
            initial_input=text,
            soft_cap=self._soft_cap,
            hard_cap=self._hard_cap,
            timeout_seconds=20.0,
            trace_readable=False,
        )

    def lifecycle_state(self, *, session_id: str) -> dict[str, Any]:
        memory_state = dict(self._collection_agent.session_store.load(session_id).state)
        return {
            "conversation_complete": bool(memory_state.get("conversation_complete", False)),
            "conversation_closing": bool(memory_state.get("conversation_closing", False)),
            "conversation_closed": bool(memory_state.get("conversation_closed", False)),
            "terminate_call": bool(memory_state.get("terminate_call", False)),
            "termination_grace_seconds": float(memory_state.get("termination_grace_seconds", 0.0) or 0.0),
        }

    def finalize_conversation(self, *, session_id: str) -> None:
        finalize_conversation_memory(self._collection_agent.session_store.load(session_id))


def _build_runtime() -> tuple[CollectionVoiceOrchestrator, PipecatRunnerConfig, dict[str, Any]]:
    config = load_collection_config(CONFIG_PATH)

    llm = build_llm(config)
    collection_agent = CollectionAgent(
        repository=CollectionRepository(runtime_dir=BASE_DIR / "runtime"),
        data_store=CollectionDataStore(base_dir=BASE_DIR),
        llm=llm,
        trace_sink=None,
        trace_output_dir=BASE_DIR / "runtime" / "traces",
    )
    discount_agent = DiscountPlanningAgent(llm=llm)
    memory_helper_agent = CollectionMemoryHelperAgent(
        repository=CollectionMemoryRepository(collection_runtime_dir=BASE_DIR / "runtime"),
        llm=llm,
    )

    runtime_cfg = PipecatRunnerConfig.from_mapping((config.get("voice_runtime") or {}).get("pipecat"))

    soft_cap = int((config.get("demo") or {}).get("agent_hop_soft_cap", 10))
    hard_cap = int((config.get("demo") or {}).get("agent_hop_hard_cap", 50))
    hard_cap = max(hard_cap, soft_cap)

    orchestrator = CollectionVoiceOrchestrator(
        collection_agent=collection_agent,
        discount_agent=discount_agent,
        memory_helper_agent=memory_helper_agent,
        soft_cap=soft_cap,
        hard_cap=hard_cap,
    )
    return orchestrator, runtime_cfg, config


def _load_runtime_cfg() -> PipecatRunnerConfig:
    """Loads only Pipecat runtime config without booting agent dependencies."""

    config = load_collection_config(CONFIG_PATH)
    return PipecatRunnerConfig.from_mapping((config.get("voice_runtime") or {}).get("pipecat"))


async def _run_bot(transport: Any, runner_args: Any) -> None:
    """Runs Pipecat pipeline and delegates final-turn responses to Collection Agent."""

    # Lazy Pipecat imports keep standard CLI paths working without pipecat installed.
    from pipecat.frames.frames import TranscriptionFrame, TTSSpeakFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
    orchestrator, runtime_cfg, config = _build_runtime()

    class CollectionTurnProcessor(FrameProcessor):
        """Consumes finalized transcriptions and injects collection responses for TTS."""

        def __init__(self, *, default_session_id: str) -> None:
            super().__init__()
            self._default_session_id = default_session_id

        async def process_frame(self, frame: Any, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)

            if isinstance(frame, TranscriptionFrame):
                finalized = bool(getattr(frame, "finalized", True))
                if not finalized:
                    return
                utterance = str(getattr(frame, "text", "")).strip()
                if not utterance:
                    return

                session_id = str(getattr(frame, "user_id", "") or self._default_session_id)
                response = orchestrator.handle_text(session_id=session_id, text=utterance)
                await self.push_frame(TTSSpeakFrame(response), FrameDirection.DOWNSTREAM)
                return

            await self.push_frame(frame, direction)

    stt = build_collection_stt_service(
        config=config,
        base_dir=BASE_DIR,
    )
    tts = build_collection_tts_service(
        config=config,
        output_sample_rate=runtime_cfg.audio_out_sample_rate,
        base_dir=BASE_DIR,
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
            CollectionTurnProcessor(default_session_id=session_id),
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
        # Some transports may not expose this callback consistently.
        pass

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


def _build_bot() -> Any:
    runtime_cfg = _load_runtime_cfg()
    from pipecat.transports.base_transport import TransportParams

    vad_analyzer = None
    if runtime_cfg.vad_enabled:
        try:
            from pipecat.audio.vad.silero import SileroVADAnalyzer

            vad_analyzer = SileroVADAnalyzer()
        except Exception:
            vad_analyzer = None

    transport_params = {
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=vad_analyzer,
        )
    }
    return build_runner_bot(run_bot=_run_bot, transport_params=transport_params)


try:
    bot = _build_bot()
except PipecatNotInstalledError:
    # Keep helper imports such as `_build_runtime()` usable even when voice
    # dependencies are absent. The actual voice entrypoint still fails fast in
    # `__main__` if Pipecat is required but not installed.
    bot = None


if __name__ == "__main__":
    if bot is None:
        bot = _build_bot()
    run_pipecat_main()
