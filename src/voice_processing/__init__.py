"""Created: 2026-04-16

Purpose: Exposes the local multi-speaker voice processing pipeline package.
"""

from .audio_processor import AudioProcessor
from .config import PipelineConfig
from .embedding_extractor import EmbeddingExtractor
from .pipeline import VoiceProcessingPipeline
from .speaker_clusterer import SpeakerClusterer
from .speaker_identifier import SpeakerIdentifier
from .transcriber import Transcriber
from .types import (
    AlignmentWord,
    AudioChunk,
    SpeakerAssignmentDecision,
    SpeakerSimilarityComparison,
    SpeechSegment,
    TranscriptTurn,
)

__all__ = [
    "AlignmentWord",
    "AudioChunk",
    "AudioProcessor",
    "EmbeddingExtractor",
    "PipelineConfig",
    "SpeakerAssignmentDecision",
    "SpeakerClusterer",
    "SpeakerIdentifier",
    "SpeakerSimilarityComparison",
    "SpeechSegment",
    "TranscriptTurn",
    "Transcriber",
    "VoiceProcessingPipeline",
]
