"""Created: 2026-04-16

Purpose: Exposes local audio model wrappers used by voice processing.
"""

from .local_ecapa import LocalEcapaEmbeddingModel
from .local_silero_vad import LocalSileroVadModel
from .local_whisper import LocalWhisperModel

__all__ = [
    "LocalEcapaEmbeddingModel",
    "LocalSileroVadModel",
    "LocalWhisperModel",
]
