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
from agents.collection_agent.repository import CollectionRepository
from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_memory_helper_agent.agent import CollectionMemoryHelperAgent
from agents.collection_memory_helper_agent.repository import CollectionMemoryRepository
from agents.discount_planning_agent.agent import DiscountPlanningAgent
from src.interfaces import PipecatRunnerConfig, build_runner_bot, build_transport_params, run_pipecat_main

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
            trace_readable=False,
        )


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
    from pipecat.services.openai.stt import OpenAISTTService
    from pipecat.services.openai.tts import OpenAITTSService

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

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for Pipecat Collection bot.")

    stt_model = str((config.get("voice_runtime") or {}).get("stt_model", "gpt-4o-mini-transcribe"))
    tts_model = str((config.get("voice_runtime") or {}).get("tts_model", "gpt-4o-mini-tts"))
    tts_voice = str((config.get("voice_runtime") or {}).get("tts_voice", "alloy"))

    stt = OpenAISTTService(api_key=openai_api_key, model=stt_model)
    tts = OpenAITTSService(api_key=openai_api_key, model=tts_model, voice=tts_voice)

    runner_body = getattr(runner_args, "body", None)
    if isinstance(runner_body, dict):
        session_id = str(runner_body.get("session_id", "")).strip() or "voice-session"
    else:
        session_id = "voice-session"

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
            await task.queue_frame(TTSSpeakFrame("Hello. This is the collections assistant. How can I help you today?"))
    except Exception:
        # Some transports may not expose this callback consistently.
        pass

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


def _build_bot() -> Any:
    runtime_cfg = _load_runtime_cfg()
    transport_params = build_transport_params(vad_enabled=runtime_cfg.vad_enabled)
    return build_runner_bot(run_bot=_run_bot, transport_params=transport_params)


bot = _build_bot()


if __name__ == "__main__":
    run_pipecat_main()
