"""Created: 2026-04-16

Purpose: Implements enrolled-speaker identification for voice processing.
"""

from __future__ import annotations

import numpy as np

from platform_logging.structured_logger import StructuredLogger
from voice_processing.config import PipelineConfig
from voice_processing.types import SpeechSegment


LOGGER = StructuredLogger("voice_processing")


class SpeakerIdentifier:
    """Assigns the known user label based on cosine similarity."""

    def __init__(self, config: PipelineConfig):
        self._config = config

    def assign_user_labels(self, segments: list[SpeechSegment], user_embedding: np.ndarray) -> list[bool]:
        """Marks segments that match the enrolled user voice."""

        labels: list[bool] = []
        for segment in segments:
            if segment.embedding is None:
                raise ValueError("Segment embedding is missing.")
            similarity = self.cosine_similarity(segment.embedding, user_embedding)
            is_user = similarity >= self._config.user_similarity_threshold
            segment.speaker_confidence = similarity
            if is_user:
                segment.speaker = "USER"
            labels.append(is_user)
        LOGGER.info("Matched %s segments to USER.", sum(labels))
        return labels

    @staticmethod
    def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
        """Computes cosine similarity between two embeddings."""

        denominator = np.linalg.norm(left) * np.linalg.norm(right)
        if denominator == 0.0:
            return 0.0
        return float(np.dot(left, right) / denominator)
