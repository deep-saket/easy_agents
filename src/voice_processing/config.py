"""Created: 2026-04-16

Purpose: Defines configuration for the local voice processing pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch


@dataclass(slots=True)
class PipelineConfig:
    """Defines runtime settings for the local voice pipeline."""

    sample_rate: int = 16000
    vad_threshold: float = 0.5
    vad_min_silence_ms: int = 250
    vad_min_speech_ms: int = 200
    vad_max_speech_s: float = 18.0
    preferred_segment_s: float = 2.0
    min_segment_s: float = 0.6
    max_segment_s: float = 3.0
    embedding_batch_size: int = 16
    user_similarity_threshold: float = 0.7
    user_margin_threshold: float = 0.04
    speaker_assignment_strategy: str = "unique_speaker_similarity"
    speaker_similarity_threshold: float = 0.72
    cluster_distance_threshold: float = 0.4
    cluster_min_size: int = 1
    whisper_model_name: str = "small"
    whisper_device: str | None = None
    whisper_compute_type: str = "float16"
    asr_chunk_s: float = 28.0
    asr_chunk_padding_s: float = 0.2
    language: str | None = None
    output_json_path: Path | None = None

    def resolve_device(self) -> str:
        """Returns the torch device string used by model-backed stages."""

        if self.whisper_device:
            return self.whisper_device
        return "cuda" if torch.cuda.is_available() else "cpu"
