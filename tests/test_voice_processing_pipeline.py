"""Created: 2026-04-16

Purpose: Verifies speaker alignment and clustering behavior for the local voice pipeline.
"""

from __future__ import annotations

import numpy as np
import torch

from voice_processing.config import PipelineConfig
from voice_processing.embedding_extractor import EmbeddingExtractor
from voice_processing.models.local_ecapa import LocalEcapaEmbeddingModel
from voice_processing.pipeline import VoiceProcessingPipeline
from voice_processing.speaker_clusterer import SpeakerClusterer
from voice_processing.types import AudioChunk
from voice_processing.types import AlignmentWord, SpeechSegment


class FakeAudioProcessor:
    def load_audio(self, path: str) -> tuple[torch.Tensor, int]:
        return torch.zeros((1, 16000), dtype=torch.float32), 16000

    def segment_speech(self, waveform: torch.Tensor) -> list[SpeechSegment]:
        return [
            SpeechSegment(start=0.0, end=1.0, audio=torch.zeros((1, 16000), dtype=torch.float32)),
            SpeechSegment(start=1.2, end=2.2, audio=torch.zeros((1, 16000), dtype=torch.float32)),
        ]

    def build_asr_chunks(self, waveform: torch.Tensor, segments: list[SpeechSegment]) -> list[AudioChunk]:
        return [AudioChunk(start=0.0, end=2.2, audio=np.zeros(35200, dtype=np.float32))]


class FakeEmbeddingExtractor:
    def extract_embeddings(self, segments: list[SpeechSegment]) -> np.ndarray:
        embeddings = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        for segment, embedding in zip(segments, embeddings, strict=False):
            segment.embedding = embedding
        return embeddings


class FakeTranscriber:
    def transcribe_chunks(self, chunks: list[AudioChunk]) -> list[AlignmentWord]:
        return [
            AlignmentWord(start=0.1, end=0.4, text="alpha"),
            AlignmentWord(start=1.3, end=1.6, text="beta"),
        ]


class FakeEmbeddingModel:
    def encode_batch(self, waveforms: torch.Tensor) -> torch.Tensor:
        assert waveforms.shape == (3, 32000)
        return torch.ones((3, 2), dtype=torch.float32)


class FakeSpeechBrainClassifier:
    def __init__(self) -> None:
        self.received_wav_lens: torch.Tensor | None = None

    def encode_batch(self, waveforms: torch.Tensor, wav_lens: torch.Tensor | None = None) -> torch.Tensor:
        self.received_wav_lens = wav_lens
        return torch.ones((waveforms.shape[0], 1, 2), dtype=torch.float32)


def test_align_words_to_speakers_merges_contiguous_turns() -> None:
    config = PipelineConfig()
    pipeline = VoiceProcessingPipeline(config=config)
    segments = [
        SpeechSegment(start=0.0, end=1.0, audio=torch.zeros((1, 1), dtype=torch.float32)),
        SpeechSegment(start=1.0, end=2.0, audio=torch.zeros((1, 1), dtype=torch.float32)),
        SpeechSegment(start=2.2, end=3.2, audio=torch.zeros((1, 1), dtype=torch.float32)),
    ]
    segments[0].speaker = "USER"
    segments[1].speaker = "USER"
    segments[2].speaker = "Speaker_0"
    words = [
        AlignmentWord(start=0.1, end=0.4, text="hello"),
        AlignmentWord(start=0.45, end=0.8, text="there"),
        AlignmentWord(start=1.2, end=1.5, text="friend"),
        AlignmentWord(start=2.3, end=2.6, text="general"),
        AlignmentWord(start=2.7, end=3.0, text="kenobi"),
    ]

    turns = pipeline.align_words_to_speakers(words, segments)

    assert [turn.speaker for turn in turns] == ["USER", "Speaker_0"]
    assert turns[0].text == "hello there friend"
    assert turns[1].text == "general kenobi"


def test_agglomerative_clusterer_orders_labels_by_first_timeline_appearance() -> None:
    config = PipelineConfig(speaker_assignment_strategy="agglomerative", cluster_distance_threshold=0.2)
    clusterer = SpeakerClusterer(config=config)
    segments = [
        SpeechSegment(start=4.0, end=5.0, audio=torch.zeros((1, 1), dtype=torch.float32)),
        SpeechSegment(start=0.0, end=1.0, audio=torch.zeros((1, 1), dtype=torch.float32)),
        SpeechSegment(start=2.0, end=3.0, audio=torch.zeros((1, 1), dtype=torch.float32)),
    ]
    segments[0].embedding = np.array([1.0, 0.0], dtype=np.float32)
    segments[1].embedding = np.array([0.0, 1.0], dtype=np.float32)
    segments[2].embedding = np.array([0.0, 0.9], dtype=np.float32)

    clusterer.cluster(segments)

    assert segments[1].speaker == "Speaker_0"
    assert segments[2].speaker == "Speaker_0"
    assert segments[0].speaker == "Speaker_1"


def test_unique_speaker_similarity_assigns_against_existing_speakers() -> None:
    config = PipelineConfig(
        speaker_assignment_strategy="unique_speaker_similarity",
        speaker_similarity_threshold=0.85,
    )
    clusterer = SpeakerClusterer(config=config)
    segments = [
        SpeechSegment(start=0.0, end=1.0, audio=torch.zeros((1, 1), dtype=torch.float32)),
        SpeechSegment(start=1.0, end=2.0, audio=torch.zeros((1, 1), dtype=torch.float32)),
        SpeechSegment(start=2.0, end=3.0, audio=torch.zeros((1, 1), dtype=torch.float32)),
        SpeechSegment(start=3.0, end=4.0, audio=torch.zeros((1, 1), dtype=torch.float32)),
    ]
    segments[0].embedding = np.array([1.0, 0.0], dtype=np.float32)
    segments[1].embedding = np.array([0.0, 1.0], dtype=np.float32)
    segments[2].embedding = np.array([0.96, 0.04], dtype=np.float32)
    segments[3].embedding = np.array([0.08, 0.92], dtype=np.float32)

    clusterer.cluster(segments)

    assert [segment.speaker for segment in segments] == [
        "Speaker_0",
        "Speaker_1",
        "Speaker_0",
        "Speaker_1",
    ]
    assert clusterer.similarity_comparisons
    assert any(comparison.matched for comparison in clusterer.similarity_comparisons)


def test_pipeline_runs_without_user_voice_path() -> None:
    config = PipelineConfig(speaker_assignment_strategy="unique_speaker_similarity", speaker_similarity_threshold=0.85)
    pipeline = VoiceProcessingPipeline(
        config=config,
        audio_processor=FakeAudioProcessor(),  # type: ignore[arg-type]
        embedding_extractor=FakeEmbeddingExtractor(),  # type: ignore[arg-type]
        transcriber=FakeTranscriber(),  # type: ignore[arg-type]
    )

    payload = pipeline.run("audio.wav")

    assert [item["speaker"] for item in payload] == ["Speaker_0", "Speaker_1"]
    assert [item["text"] for item in payload] == ["alpha", "beta"]


def test_embedding_extractor_pads_variable_length_batch_segments() -> None:
    extractor = EmbeddingExtractor(
        PipelineConfig(embedding_batch_size=3),
        embedding_model=FakeEmbeddingModel(),  # type: ignore[arg-type]
    )
    segments = [
        SpeechSegment(start=0.0, end=2.0, audio=torch.zeros((1, 32000), dtype=torch.float32)),
        SpeechSegment(start=2.0, end=3.5, audio=torch.zeros((1, 24000), dtype=torch.float32)),
        SpeechSegment(start=3.5, end=4.52, audio=torch.zeros((1, 16320), dtype=torch.float32)),
    ]

    embeddings = extractor.extract_embeddings(segments)

    assert embeddings.shape == (3, 2)
    assert all(segment.embedding is not None for segment in segments)


def test_local_ecapa_uses_speechbrain_wav_lens_signature() -> None:
    classifier = FakeSpeechBrainClassifier()
    model = LocalEcapaEmbeddingModel(PipelineConfig(whisper_device="cpu"))
    model._classifier = classifier

    embeddings = model.encode_batch(torch.zeros((2, 16000), dtype=torch.float32))

    assert embeddings.shape == (2, 2)
    assert classifier.received_wav_lens is not None
    assert classifier.received_wav_lens.tolist() == [1.0, 1.0]
