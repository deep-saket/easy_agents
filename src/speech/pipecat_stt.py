"""Pipecat STT backend selection for Collection Agent voice runtimes."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
from typing import Any


def _resolve_whisper_language(language_value: str | None) -> Any | None:
    if not isinstance(language_value, str) or not language_value.strip():
        return None
    from pipecat.transcriptions.language import Language

    normalized = language_value.strip()
    candidate_keys = [
        normalized.upper().replace("-", "_"),
        normalized.lower().replace("-", "_"),
    ]
    for key in candidate_keys:
        if hasattr(Language, key):
            return getattr(Language, key)
    return None


def build_collection_stt_service(
    *,
    config: Mapping[str, Any],
    base_dir: Path | None = None,
) -> Any:
    """Builds the configured STT service for Collection Agent voice runtimes."""

    del base_dir  # reserved for future local artifact resolution
    voice_cfg = dict(config.get("voice_runtime", {})) if isinstance(config.get("voice_runtime"), Mapping) else {}
    backend = str(voice_cfg.get("stt_backend", "whisper_local")).strip().lower()

    if backend == "nvidia":
        from pipecat.services.nvidia.stt import NvidiaSTTService

        nvidia_api_key = os.getenv("NVIDIA_API_KEY", "").strip()
        if not nvidia_api_key:
            raise ValueError("NVIDIA_API_KEY is required for the NVIDIA STT backend.")
        model_name = str(voice_cfg.get("stt_model", "nvidia_default")).strip()
        model_function_map = None
        if model_name and model_name != "nvidia_default":
            model_function_map = {"model_name": model_name}
        if model_function_map:
            return NvidiaSTTService(api_key=nvidia_api_key, model_function_map=model_function_map)
        return NvidiaSTTService(api_key=nvidia_api_key)

    if backend in {"whisper_local", "local_whisper"}:
        from pipecat.services.whisper.stt import WhisperSTTService

        whisper_cfg = dict(voice_cfg.get("local_stt", {})) if isinstance(voice_cfg.get("local_stt"), Mapping) else {}
        model = str(whisper_cfg.get("model", "base")).strip() or "base"
        device = str(whisper_cfg.get("device", "auto")).strip() or "auto"
        compute_type = str(whisper_cfg.get("compute_type", "default")).strip() or "default"
        no_speech_prob = whisper_cfg.get("no_speech_prob")
        language = _resolve_whisper_language(whisper_cfg.get("language"))
        kwargs: dict[str, Any] = {
            "model": model,
            "device": device,
            "compute_type": compute_type,
        }
        if isinstance(no_speech_prob, (int, float)):
            kwargs["no_speech_prob"] = float(no_speech_prob)
        if language is not None:
            kwargs["language"] = language
        return WhisperSTTService(**kwargs)

    raise ValueError(
        "voice_runtime.stt_backend must be one of: 'whisper_local', 'nvidia'. "
        f"Got: {backend}"
    )
