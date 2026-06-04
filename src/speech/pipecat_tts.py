"""Pipecat TTS backend selection for Collection Agent voice runtimes."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import os
from pathlib import Path
from typing import Any, AsyncGenerator

from .speecht5_tts import SpeechT5Synthesizer, SpeechT5TTSConfig


def _pcm16_bytes(waveform: Any) -> bytes:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional runtime
        raise ModuleNotFoundError(
            "numpy is required for local SpeechT5 synthesis. Install the 'voice-local-tts' optional dependency."
        ) from exc
    clipped = np.clip(waveform, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    return pcm.tobytes()


def _resample_waveform(waveform: Any, *, input_rate: int, output_rate: int) -> Any:
    if input_rate == output_rate:
        return waveform
    try:
        import torch
        import torchaudio
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional runtime
        raise ModuleNotFoundError(
            "torchaudio is required to resample local SpeechT5 output. "
            "Install the 'voice-local-tts' optional dependency."
        ) from exc
    tensor = torch.tensor(waveform).reshape(1, -1)
    resampled = torchaudio.functional.resample(tensor, orig_freq=input_rate, new_freq=output_rate)
    return resampled.squeeze(0).cpu().numpy().astype("float32")


class LocalSpeechT5PipecatTTSService:
    """Pipecat-compatible TTS service that synthesizes locally with SpeechT5."""

    def __init__(
        self,
        *,
        config: SpeechT5TTSConfig,
        output_sample_rate: int,
        chunk_duration_ms: int = 250,
    ) -> None:
        from pipecat.services.tts_service import TTSService

        class _Service(TTSService):
            def __init__(self, outer: "LocalSpeechT5PipecatTTSService") -> None:
                super().__init__(
                    sample_rate=outer.output_sample_rate,
                    push_start_frame=True,
                    push_stop_frames=True,
                )
                self._outer = outer

            async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Any, None]:
                from pipecat.frames.frames import ErrorFrame, TTSAudioRawFrame

                if not text.strip():
                    return
                try:
                    if hasattr(self, "start_ttfb_metrics"):
                        await self.start_ttfb_metrics()
                    waveform = await asyncio.to_thread(self._outer._synthesize, text)
                    if hasattr(self, "stop_ttfb_metrics"):
                        await self.stop_ttfb_metrics()
                    pcm = _pcm16_bytes(waveform)
                    for chunk in self._outer._chunk_pcm(pcm):
                        yield TTSAudioRawFrame(
                            audio=chunk,
                            sample_rate=self._outer.output_sample_rate,
                            num_channels=1,
                        )
                except Exception as exc:  # pragma: no cover - runtime integration path
                    yield ErrorFrame(error=str(exc))

        self.output_sample_rate = int(output_sample_rate)
        self.chunk_duration_ms = max(int(chunk_duration_ms), 50)
        self.config = config
        self._synthesizer = SpeechT5Synthesizer(config)
        self.service = _Service(self)

    def _synthesize(self, text: str) -> Any:
        waveform = self._synthesizer.synthesize(text)
        return _resample_waveform(
            waveform,
            input_rate=self.config.model_sample_rate,
            output_rate=self.output_sample_rate,
        )

    def _chunk_pcm(self, pcm_bytes: bytes) -> list[bytes]:
        bytes_per_sample = 2
        samples_per_chunk = max(int(self.output_sample_rate * (self.chunk_duration_ms / 1000.0)), 1)
        chunk_bytes = samples_per_chunk * bytes_per_sample
        return [pcm_bytes[idx : idx + chunk_bytes] for idx in range(0, len(pcm_bytes), chunk_bytes)]


def build_collection_tts_service(
    *,
    config: Mapping[str, Any],
    output_sample_rate: int,
    base_dir: Path | None = None,
) -> Any:
    """Builds the configured TTS service for Collection Agent voice runtimes."""

    voice_cfg = dict(config.get("voice_runtime", {})) if isinstance(config.get("voice_runtime"), Mapping) else {}
    backend = str(voice_cfg.get("tts_backend", "speecht5_local")).strip().lower()

    if backend == "nvidia":
        from pipecat.services.nvidia.tts import NvidiaTTSService

        nvidia_api_key = os.getenv("NVIDIA_API_KEY", "").strip()
        if not nvidia_api_key:
            raise ValueError("NVIDIA_API_KEY is required for the NVIDIA TTS backend.")
        model_name = str(voice_cfg.get("tts_model", "nvidia_default")).strip()
        voice_id = str(voice_cfg.get("tts_voice", "nvidia_default")).strip()
        kwargs: dict[str, Any] = {"api_key": nvidia_api_key}
        if model_name and model_name != "nvidia_default":
            kwargs["model_function_map"] = {"model_name": model_name}
        if voice_id and voice_id != "nvidia_default":
            kwargs["voice_id"] = voice_id
        return NvidiaTTSService(**kwargs)

    if backend in {"speecht5_local", "local_speecht5"}:
        local_cfg = SpeechT5TTSConfig.from_mapping(voice_cfg.get("local_tts"), base_dir=base_dir)
        wrapper = LocalSpeechT5PipecatTTSService(
            config=local_cfg,
            output_sample_rate=int(output_sample_rate),
        )
        return wrapper.service

    raise ValueError(
        "voice_runtime.tts_backend must be one of: 'nvidia', 'speecht5_local'. "
        f"Got: {backend}"
    )
