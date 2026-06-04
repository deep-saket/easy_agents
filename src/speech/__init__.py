"""Speech runtime helpers for local TTS and speaker embeddings."""

from .embedding_loader import (
    SpeakerEmbeddingSource,
    load_speaker_embedding,
    save_speaker_embedding_from_audio,
    save_speaker_embedding_from_hf_dataset,
)
from .pipecat_stt import build_collection_stt_service
from .pipecat_tts import build_collection_tts_service
from .speecht5_tts import SpeechT5TTSConfig, SpeechT5Synthesizer

__all__ = [
    "SpeakerEmbeddingSource",
    "SpeechT5Synthesizer",
    "SpeechT5TTSConfig",
    "build_collection_stt_service",
    "build_collection_tts_service",
    "load_speaker_embedding",
    "save_speaker_embedding_from_audio",
    "save_speaker_embedding_from_hf_dataset",
]
