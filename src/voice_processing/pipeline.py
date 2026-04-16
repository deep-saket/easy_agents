"""Created: 2026-04-16

Purpose: Coordinates the local multi-speaker voice processing pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from platform_logging.structured_logger import StructuredLogger
from voice_processing.audio_processor import AudioProcessor
from voice_processing.config import PipelineConfig
from voice_processing.embedding_extractor import EmbeddingExtractor
from voice_processing.speaker_clusterer import SpeakerClusterer
from voice_processing.speaker_identifier import SpeakerIdentifier
from voice_processing.transcriber import Transcriber
from voice_processing.types import (
    AlignmentWord,
    SpeakerAssignmentDecision,
    SpeakerSimilarityComparison,
    SpeechSegment,
    TranscriptTurn,
)


LOGGER = StructuredLogger("voice_processing")


class VoiceProcessingPipeline:
    """Coordinates local diarization, user identification, and ASR."""

    def __init__(
        self,
        config: PipelineConfig | None = None,
        audio_processor: AudioProcessor | None = None,
        embedding_extractor: EmbeddingExtractor | None = None,
        speaker_identifier: SpeakerIdentifier | None = None,
        speaker_clusterer: SpeakerClusterer | None = None,
        transcriber: Transcriber | None = None,
    ):
        self._config = config or PipelineConfig()
        self._audio_processor = audio_processor or AudioProcessor(self._config)
        self._embedding_extractor = embedding_extractor or EmbeddingExtractor(self._config)
        self._speaker_identifier = speaker_identifier or SpeakerIdentifier(self._config)
        self._speaker_clusterer = speaker_clusterer or SpeakerClusterer(self._config)
        self._transcriber = transcriber or Transcriber(self._config)

    def run(self, audio_path: str | Path, user_voice_path: str | Path | None = None) -> list[dict[str, Any]]:
        """Runs the full voice processing pipeline on local files."""

        LOGGER.info("Loading source audio from %s.", audio_path)
        waveform, _ = self._audio_processor.load_audio(audio_path)

        speech_segments = self._audio_processor.segment_speech(waveform)
        if not speech_segments:
            return []

        self._embedding_extractor.extract_embeddings(speech_segments)
        if user_voice_path is not None:
            self._assign_user_labels(user_voice_path, speech_segments)
        else:
            LOGGER.info("No user enrollment audio provided. Running clustering-only diarization.")
        self._speaker_clusterer.cluster(speech_segments)

        asr_chunks = self._audio_processor.build_asr_chunks(waveform, speech_segments)
        words = self._transcriber.transcribe_chunks(asr_chunks)

        transcript_turns = self.align_words_to_speakers(words, speech_segments)
        payload = [self._turn_to_dict(turn) for turn in transcript_turns]
        self._emit_outputs(payload)
        return payload

    @property
    def speaker_similarity_comparisons(self) -> list[SpeakerSimilarityComparison]:
        """Returns post-diarization speaker merge comparison records."""

        return list(self._speaker_clusterer.similarity_comparisons)

    @property
    def speaker_assignment_decisions(self) -> list[SpeakerAssignmentDecision]:
        """Returns final segment-to-speaker assignment decisions."""

        return list(self._speaker_clusterer.assignment_decisions)

    def _emit_speaker_assignments(self) -> None:
        """Prints final unique-speaker assignment decisions."""

        decisions = self.speaker_assignment_decisions
        if not decisions:
            return
        print("Speaker assignment decisions:")
        for decision in decisions:
            if decision.similarity is None or decision.confidence is None:
                print(f"{decision.provisional_speaker} assigned to {decision.assigned_speaker} (first unique speaker)")
                continue
            action = "matched existing" if decision.matched_existing else "created new speaker"
            print(
                f"{decision.provisional_speaker} assigned to {decision.assigned_speaker} "
                f"({action}, similarity={decision.similarity:.4f}, "
                f"threshold={decision.threshold:.4f}, confidence={decision.confidence:.4f})"
            )

    def _assign_user_labels(self, user_voice_path: str | Path, speech_segments: list[SpeechSegment]) -> None:
        LOGGER.info("Loading user enrollment audio from %s.", user_voice_path)
        user_waveform, _ = self._audio_processor.load_audio(user_voice_path)
        user_segments = self._audio_processor.segment_speech(user_waveform)
        if user_segments:
            user_embeddings = self._embedding_extractor.extract_embeddings(user_segments)
            user_embedding = self._embedding_extractor.average_embeddings(user_embeddings)
        else:
            LOGGER.warning("No speech detected in user enrollment audio. Falling back to full-file embedding.")
            user_embedding = self._embedding_extractor.extract_reference_embedding(user_waveform)
        self._speaker_identifier.assign_user_labels(speech_segments, user_embedding)

    def align_words_to_speakers(
        self,
        words: list[AlignmentWord],
        segments: list[SpeechSegment],
    ) -> list[TranscriptTurn]:
        """Assigns each word to the best-overlapping speaker segment."""

        if not words or not segments:
            return []

        speaker_words: list[tuple[str, AlignmentWord]] = []
        for word in words:
            speaker = self._resolve_word_speaker(word, segments)
            if speaker is None:
                continue
            speaker_words.append((speaker, word))

        if not speaker_words:
            return []

        turns: list[TranscriptTurn] = []
        current_speaker, first_word = speaker_words[0]
        current_words = [first_word.text]
        current_start = first_word.start
        current_end = first_word.end

        for speaker, word in speaker_words[1:]:
            is_continuation = speaker == current_speaker and word.start - current_end <= 1.0
            if is_continuation:
                current_words.append(word.text)
                current_end = max(current_end, word.end)
                continue
            turns.append(
                TranscriptTurn(
                    start=current_start,
                    end=current_end,
                    speaker=current_speaker,
                    text=self._join_words(current_words),
                )
            )
            current_speaker = speaker
            current_words = [word.text]
            current_start = word.start
            current_end = word.end

        turns.append(
            TranscriptTurn(
                start=current_start,
                end=current_end,
                speaker=current_speaker,
                text=self._join_words(current_words),
            )
        )
        return turns

    def _resolve_word_speaker(self, word: AlignmentWord, segments: list[SpeechSegment]) -> str | None:
        candidates: list[tuple[float, float, SpeechSegment]] = []
        word_midpoint = (word.start + word.end) / 2.0
        for segment in segments:
            overlap = min(word.end, segment.end) - max(word.start, segment.start)
            if overlap > 0:
                midpoint_distance = abs(word_midpoint - ((segment.start + segment.end) / 2.0))
                candidates.append((overlap, -midpoint_distance, segment))
        if candidates:
            best_segment = max(candidates, key=lambda item: (item[0], item[1]))[2]
            return best_segment.speaker

        nearest = min(
            segments,
            key=lambda segment: min(abs(word.start - segment.end), abs(word.end - segment.start)),
        )
        if min(abs(word.start - nearest.end), abs(word.end - nearest.start)) <= 0.35:
            return nearest.speaker
        return None

    def _emit_outputs(self, payload: list[dict[str, Any]]) -> None:
        readable = "\n".join(
            f"[{item['start']:.2f}-{item['end']:.2f}] {item['speaker']}: {item['text']}" for item in payload
        )
        if readable:
            print(readable)
        else:
            print("No aligned transcript segments found.")
        if self._config.output_json_path is not None:
            self._config.output_json_path.parent.mkdir(parents=True, exist_ok=True)
            self._config.output_json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            LOGGER.info("Wrote JSON transcript to %s.", self._config.output_json_path)

    def _turn_to_dict(self, turn: TranscriptTurn) -> dict[str, Any]:
        return {
            "start": round(turn.start, 3),
            "end": round(turn.end, 3),
            "speaker": turn.speaker,
            "text": turn.text,
        }

    @staticmethod
    def _join_words(words: list[str]) -> str:
        text = " ".join(words)
        replacements = {
            " ,": ",",
            " .": ".",
            " !": "!",
            " ?": "?",
            " ;": ";",
            " :": ":",
            " n't": "n't",
            " 's": "'s",
            " 're": "'re",
            " 've": "'ve",
            " 'm": "'m",
            " 'll": "'ll",
            " 'd": "'d",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text.strip()
