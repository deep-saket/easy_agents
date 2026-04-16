"""Created: 2026-04-16

Purpose: Wraps the local SpeechBrain ECAPA speaker embedding model.
"""

from __future__ import annotations

import inspect
from typing import Any

import torch

from voice_processing.config import PipelineConfig


class LocalEcapaEmbeddingModel:
    """Loads and runs SpeechBrain ECAPA-TDNN speaker embeddings locally."""

    def __init__(self, config: PipelineConfig):
        self._config = config
        self._device = config.resolve_device()
        self._classifier: Any | None = None

    def encode_batch(self, waveforms: torch.Tensor) -> torch.Tensor:
        """Encodes a batch of waveforms into speaker embeddings."""

        classifier = self._load_classifier()
        wav_lens = torch.ones(waveforms.shape[0], device=self._device)
        model_input = waveforms.to(self._device)
        with torch.inference_mode():
            if "wav_lens" in inspect.signature(classifier.encode_batch).parameters:
                encoded = classifier.encode_batch(model_input, wav_lens=wav_lens)
            else:
                encoded = classifier.encode_batch(model_input, lengths=wav_lens)
        return encoded.squeeze(1).detach().cpu()

    def _load_classifier(self) -> Any:
        if self._classifier is not None:
            return self._classifier
        try:
            from speechbrain.inference.speaker import EncoderClassifier
        except ImportError as error:
            raise ImportError(
                "speechbrain is required for speaker embeddings. Install the 'voice-processing' optional dependency."
            ) from error

        self._classifier = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            run_opts={"device": self._device},
        )
        return self._classifier
