"""Created: 2026-04-16

Purpose: Implements local Whisper transcription for voice processing.
"""

from __future__ import annotations

from platform_logging.structured_logger import StructuredLogger
from voice_processing.config import PipelineConfig
from voice_processing.models import LocalWhisperModel
from voice_processing.types import AlignmentWord, AudioChunk


LOGGER = StructuredLogger("voice_processing")


class Transcriber:
    """Runs local Whisper transcription and returns word timestamps."""

    def __init__(self, config: PipelineConfig, whisper_model: LocalWhisperModel | None = None):
        self._config = config
        self._whisper_model = whisper_model or LocalWhisperModel(config)

    def transcribe_chunks(self, chunks: list[AudioChunk]) -> list[AlignmentWord]:
        """Transcribes audio chunks and returns timeline-aligned words."""

        if not chunks:
            return []
        words: list[AlignmentWord] = []
        for chunk in chunks:
            result = self._whisper_model.transcribe(chunk.audio)
            for segment in result.get("segments", []):
                for word in segment.get("words", []):
                    token = (word.get("word") or "").strip()
                    if not token:
                        continue
                    words.append(
                        AlignmentWord(
                            start=chunk.start + float(word["start"]),
                            end=chunk.start + float(word["end"]),
                            text=token,
                            confidence=float(word.get("probability")) if word.get("probability") is not None else None,
                        )
                    )
        LOGGER.info("Transcribed %s timestamped words.", len(words))
        return self._deduplicate_boundary_words(words)

    def _deduplicate_boundary_words(self, words: list[AlignmentWord]) -> list[AlignmentWord]:
        if not words:
            return []
        words = sorted(words, key=lambda item: (item.start, item.end, item.text))
        deduplicated: list[AlignmentWord] = [words[0]]
        for word in words[1:]:
            previous = deduplicated[-1]
            if word.text == previous.text and abs(word.start - previous.start) < 0.08 and abs(word.end - previous.end) < 0.08:
                continue
            deduplicated.append(word)
        return deduplicated
