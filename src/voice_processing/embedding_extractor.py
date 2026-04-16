"""Created: 2026-04-16

Purpose: Implements batched local speaker embedding extraction.
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F

from platform_logging.structured_logger import StructuredLogger
from voice_processing.config import PipelineConfig
from voice_processing.models import LocalEcapaEmbeddingModel
from voice_processing.types import SpeechSegment


LOGGER = StructuredLogger("voice_processing")


class EmbeddingExtractor:
    """Generates speaker embeddings from audio segments."""

    def __init__(self, config: PipelineConfig, embedding_model: LocalEcapaEmbeddingModel | None = None):
        self._config = config
        self._embedding_model = embedding_model or LocalEcapaEmbeddingModel(config)

    def extract_embeddings(self, segments: list[SpeechSegment]) -> np.ndarray:
        """Computes one embedding for each speech segment."""

        if not segments:
            return np.empty((0, 0), dtype=np.float32)

        embeddings: list[np.ndarray] = []
        batch_size = self._config.embedding_batch_size
        for batch_start in range(0, len(segments), batch_size):
            batch = segments[batch_start : batch_start + batch_size]
            batch_waveforms = self._prepare_batch(batch)
            encoded = self._embedding_model.encode_batch(batch_waveforms)
            normalized = F.normalize(encoded, dim=-1)
            for segment, embedding in zip(batch, normalized.numpy(), strict=False):
                segment.embedding = embedding.astype(np.float32)
                embeddings.append(segment.embedding)
        LOGGER.info("Computed %s speaker embeddings.", len(embeddings))
        return np.stack(embeddings, axis=0)

    def extract_reference_embedding(self, waveform: torch.Tensor) -> np.ndarray:
        """Computes the enrolled embedding for the known user voice."""

        segment = SpeechSegment(
            start=0.0,
            end=waveform.shape[-1] / self._config.sample_rate,
            audio=waveform,
        )
        return self.extract_embeddings([segment])[0]

    def average_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """Averages and normalizes multiple embeddings into one reference vector."""

        if embeddings.ndim != 2 or embeddings.shape[0] == 0:
            raise ValueError("Expected a non-empty 2D embedding matrix.")
        mean_embedding = embeddings.mean(axis=0)
        denominator = np.linalg.norm(mean_embedding)
        if denominator == 0.0:
            return mean_embedding.astype(np.float32)
        return (mean_embedding / denominator).astype(np.float32)

    def _prepare_audio(self, audio: torch.Tensor) -> torch.Tensor:
        min_samples = int(self._config.min_segment_s * self._config.sample_rate)
        if audio.shape[-1] >= min_samples:
            return audio
        repeat_factor = int(np.ceil(min_samples / audio.shape[-1]))
        return audio.repeat(repeat_factor)[:min_samples]

    def _prepare_batch(self, segments: list[SpeechSegment]) -> torch.Tensor:
        waveforms = [self._prepare_audio(segment.audio.squeeze(0)) for segment in segments]
        max_samples = max(waveform.shape[-1] for waveform in waveforms)
        padded = [
            F.pad(waveform, (0, max_samples - waveform.shape[-1]))
            if waveform.shape[-1] < max_samples
            else waveform
            for waveform in waveforms
        ]
        return torch.stack(padded, dim=0)
