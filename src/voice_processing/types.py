"""Created: 2026-04-16

Purpose: Defines shared data models for local voice processing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch


@dataclass(slots=True)
class SpeechSegment:
    """Represents a speech region on the timeline."""

    start: float
    end: float
    audio: torch.Tensor
    embedding: np.ndarray | None = None
    speaker: str | None = None
    speaker_confidence: float | None = None

    @property
    def duration(self) -> float:
        """Returns the segment length in seconds."""

        return max(0.0, self.end - self.start)


@dataclass(slots=True)
class AudioChunk:
    """Represents an ASR chunk cut from the timeline."""

    start: float
    end: float
    audio: np.ndarray


@dataclass(slots=True)
class AlignmentWord:
    """Represents a timestamped transcript token."""

    start: float
    end: float
    text: str
    confidence: float | None = None


@dataclass(slots=True)
class TranscriptTurn:
    """Represents one output speaker turn."""

    start: float
    end: float
    speaker: str
    text: str


@dataclass(slots=True)
class SpeakerSimilarityComparison:
    """Represents one speaker-to-unique-speaker similarity decision.

    The voice pipeline uses this model to expose the post-diarization merge
    pass. Each record says which provisional speaker was compared with which
    unique speaker, the cosine similarity between their centroids, and whether
    the provisional speaker was merged into the existing unique speaker.
    """

    candidate_speaker: str
    unique_speaker: str
    similarity: float
    threshold: float
    confidence: float
    matched: bool


@dataclass(slots=True)
class SpeakerAssignmentDecision:
    """Represents the final assignment for one provisional speaker.

    A decision is emitted after the unique-speaker assignment logic decides
    whether a provisional speaker belongs to an existing unique speaker or
    should create a new unique speaker label.
    """

    provisional_speaker: str
    assigned_speaker: str
    similarity: float | None
    threshold: float
    confidence: float | None
    matched_existing: bool
