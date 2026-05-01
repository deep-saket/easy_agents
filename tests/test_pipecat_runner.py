"""Created: 2026-05-01

Purpose: Tests shared Pipecat runner integration helpers.
"""

from __future__ import annotations

import importlib

import pytest

from src.interfaces.pipecat_runner import PipecatNotInstalledError, PipecatRunnerConfig, ensure_pipecat_available


def test_pipecat_runner_config_from_mapping_defaults() -> None:
    cfg = PipecatRunnerConfig.from_mapping(None)

    assert cfg.enabled is False
    assert cfg.vad_enabled is True
    assert cfg.audio_in_sample_rate == 16000
    assert cfg.audio_out_sample_rate == 24000


def test_pipecat_runner_config_from_mapping_values() -> None:
    cfg = PipecatRunnerConfig.from_mapping(
        {
            "enabled": True,
            "vad_enabled": False,
            "audio_in_sample_rate": 8000,
            "audio_out_sample_rate": 8000,
        }
    )

    assert cfg.enabled is True
    assert cfg.vad_enabled is False
    assert cfg.audio_in_sample_rate == 8000
    assert cfg.audio_out_sample_rate == 8000


def test_ensure_pipecat_available_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    original = importlib.import_module

    def fake_import(name: str, package: str | None = None):
        if name == "pipecat":
            raise ModuleNotFoundError("No module named 'pipecat'")
        return original(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import)

    with pytest.raises(PipecatNotInstalledError):
        ensure_pipecat_available()
