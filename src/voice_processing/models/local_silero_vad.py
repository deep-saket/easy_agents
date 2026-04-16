"""Created: 2026-04-16

Purpose: Wraps the local Silero VAD model behind a small interface.
"""

from __future__ import annotations

from typing import Any

import torch

from voice_processing.config import PipelineConfig


class LocalSileroVadModel:
    """Loads and runs Silero VAD locally."""

    def __init__(self, config: PipelineConfig):
        self._config = config
        self._model: Any | None = None
        self._get_speech_timestamps: Any | None = None

    def detect(self, waveform: torch.Tensor) -> list[dict[str, int]]:
        """Returns speech timestamps in samples for a mono waveform."""

        model, get_speech_timestamps = self._load()
        return get_speech_timestamps(
            waveform.squeeze(0).cpu(),
            model,
            threshold=self._config.vad_threshold,
            sampling_rate=self._config.sample_rate,
            min_silence_duration_ms=self._config.vad_min_silence_ms,
            min_speech_duration_ms=self._config.vad_min_speech_ms,
            max_speech_duration_s=self._config.vad_max_speech_s,
            return_seconds=False,
        )

    def _load(self) -> tuple[Any, Any]:
        if self._model is not None and self._get_speech_timestamps is not None:
            return self._model, self._get_speech_timestamps
        try:
            from silero_vad import get_speech_timestamps, load_silero_vad
        except ImportError as error:
            raise ImportError(
                "silero-vad is required for VAD. Install the 'voice-processing' optional dependency."
            ) from error

        self._model = load_silero_vad()
        self._get_speech_timestamps = get_speech_timestamps
        return self._model, self._get_speech_timestamps
