"""Created: 2026-04-16

Purpose: Implements audio loading, normalization, VAD segmentation, and ASR chunking.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch

from platform_logging.structured_logger import StructuredLogger
from voice_processing.config import PipelineConfig
from voice_processing.models import LocalSileroVadModel
from voice_processing.types import AudioChunk, SpeechSegment


LOGGER = StructuredLogger("voice_processing")


class AudioProcessor:
    """Loads, normalizes, segments, and chunks waveform audio."""

    def __init__(self, config: PipelineConfig, vad_model: LocalSileroVadModel | None = None):
        self._config = config
        self._vad_model = vad_model or LocalSileroVadModel(config)

    def load_audio(self, path: str | Path) -> tuple[torch.Tensor, int]:
        """Loads and standardizes an audio file."""

        waveform, sample_rate = self._load_with_soundfile(path)
        if waveform.numel() == 0:
            raise ValueError(f"Audio file {path} is empty.")
        waveform = self._to_mono(waveform)
        waveform = self._resample_if_needed(waveform, sample_rate)
        waveform = self._normalize(waveform)
        return waveform, self._config.sample_rate

    def segment_speech(self, waveform: torch.Tensor) -> list[SpeechSegment]:
        """Runs VAD and returns embedding-friendly speech segments."""

        timestamps = self._vad_model.detect(waveform)
        if not timestamps:
            LOGGER.warning("No speech detected by VAD.")
            return []

        segments: list[SpeechSegment] = []
        for item in timestamps:
            start = item["start"] / self._config.sample_rate
            end = item["end"] / self._config.sample_rate
            segments.extend(self._split_interval(waveform, start, end))
        filtered = [segment for segment in segments if segment.duration >= self._config.min_segment_s]
        if not filtered:
            LOGGER.warning("Speech was detected, but all segments were shorter than the minimum duration.")
        LOGGER.info("VAD produced %s speech segments.", len(filtered))
        return filtered

    def build_asr_chunks(self, waveform: torch.Tensor, segments: list[SpeechSegment]) -> list[AudioChunk]:
        """Builds long-form ASR chunks from speech segments."""

        if not segments:
            return []

        chunks: list[AudioChunk] = []
        current_start = max(0.0, segments[0].start - self._config.asr_chunk_padding_s)
        current_end = min(self._duration_seconds(waveform), segments[0].end + self._config.asr_chunk_padding_s)
        for segment in segments[1:]:
            proposed_end = min(self._duration_seconds(waveform), segment.end + self._config.asr_chunk_padding_s)
            gap = segment.start - current_end
            if proposed_end - current_start <= self._config.asr_chunk_s and gap <= 1.0:
                current_end = proposed_end
                continue
            chunks.append(self._slice_chunk(waveform, current_start, current_end))
            current_start = max(0.0, segment.start - self._config.asr_chunk_padding_s)
            current_end = proposed_end
        chunks.append(self._slice_chunk(waveform, current_start, current_end))
        LOGGER.info("Prepared %s ASR chunks.", len(chunks))
        return chunks

    def _split_interval(self, waveform: torch.Tensor, start: float, end: float) -> list[SpeechSegment]:
        duration = max(0.0, end - start)
        if duration < self._config.min_segment_s:
            return []

        boundaries = [start]
        if duration <= self._config.max_segment_s:
            boundaries.append(end)
        else:
            cursor = start
            while cursor < end:
                remaining = end - cursor
                step = min(self._config.preferred_segment_s, remaining)
                if remaining - step < self._config.min_segment_s:
                    step = remaining
                boundaries.append(min(end, cursor + step))
                cursor += step

        segments: list[SpeechSegment] = []
        for left, right in zip(boundaries[:-1], boundaries[1:], strict=False):
            if right - left < self._config.min_segment_s:
                continue
            sample_start = int(left * self._config.sample_rate)
            sample_end = int(right * self._config.sample_rate)
            segments.append(SpeechSegment(start=left, end=right, audio=waveform[:, sample_start:sample_end]))
        return segments

    def _slice_chunk(self, waveform: torch.Tensor, start: float, end: float) -> AudioChunk:
        sample_start = int(start * self._config.sample_rate)
        sample_end = int(end * self._config.sample_rate)
        audio = waveform[:, sample_start:sample_end].squeeze(0).cpu().numpy().astype(np.float32)
        return AudioChunk(start=start, end=end, audio=audio)

    def _to_mono(self, waveform: torch.Tensor) -> torch.Tensor:
        if waveform.shape[0] == 1:
            return waveform
        return waveform.mean(dim=0, keepdim=True)

    def _load_with_soundfile(self, path: str | Path) -> tuple[torch.Tensor, int]:
        try:
            import soundfile as sf
        except ImportError as error:
            raise ImportError(
                "soundfile is required for audio loading. Install the 'voice-processing' optional dependency."
            ) from error

        audio, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
        waveform = torch.from_numpy(audio.T.copy())
        return waveform, int(sample_rate)

    def _resample_if_needed(self, waveform: torch.Tensor, sample_rate: int) -> torch.Tensor:
        if sample_rate == self._config.sample_rate:
            return waveform
        torchaudio_module = self._import_torchaudio()
        resampler = torchaudio_module.transforms.Resample(orig_freq=sample_rate, new_freq=self._config.sample_rate)
        return resampler(waveform)

    def _normalize(self, waveform: torch.Tensor) -> torch.Tensor:
        peak = waveform.abs().max().item()
        if peak == 0.0:
            return waveform
        return (waveform / peak).clamp_(-1.0, 1.0)

    def _duration_seconds(self, waveform: torch.Tensor) -> float:
        return waveform.shape[-1] / self._config.sample_rate

    def _import_torchaudio(self) -> Any:
        try:
            import torchaudio
        except ImportError as error:
            raise ImportError(
                "torchaudio is required for audio loading. Install the 'voice-processing' optional dependency."
            ) from error
        return torchaudio
