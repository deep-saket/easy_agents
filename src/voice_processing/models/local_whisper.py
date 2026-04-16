"""Created: 2026-04-16

Purpose: Wraps the local Whisper ASR model.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np

from voice_processing.config import PipelineConfig


class LocalWhisperModel:
    """Loads and runs OpenAI Whisper locally for ASR."""

    def __init__(self, config: PipelineConfig):
        self._config = config
        self._model: Any | None = None

    def transcribe(self, audio: np.ndarray) -> dict[str, Any]:
        """Transcribes audio and returns Whisper's structured output."""

        model = self._load_model()
        return model.transcribe(
            audio,
            language=self._config.language,
            task="transcribe",
            word_timestamps=True,
            condition_on_previous_text=False,
            verbose=False,
        )

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        self._configure_certificates()
        try:
            import whisper
        except ImportError as error:
            raise ImportError(
                "openai-whisper is required for transcription. Install the 'voice-processing' optional dependency."
            ) from error

        self._model = whisper.load_model(self._config.whisper_model_name, device=self._config.resolve_device())
        return self._model

    def _configure_certificates(self) -> None:
        try:
            import certifi
        except ImportError:
            return
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
