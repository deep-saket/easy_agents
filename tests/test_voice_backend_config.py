from __future__ import annotations

from pathlib import Path

import yaml

from src.speech.speecht5_tts import SpeechT5Synthesizer


def test_collection_voice_defaults_use_local_backends() -> None:
    config = yaml.safe_load(
        Path("/Users/saketm10/Projects/openclaw_agents/agents/collection_agent/config.yml").read_text(
            encoding="utf-8"
        )
    )
    voice_cfg = config["voice_runtime"]
    assert voice_cfg["stt_backend"] == "whisper_local"
    assert voice_cfg["tts_backend"] == "speecht5_local"
    assert voice_cfg["local_stt"]["model"] == "medium"
    assert voice_cfg["local_stt"]["compute_type"] == "int8"
    assert voice_cfg["local_tts"]["device"] == "auto"


class _FakeBackend:
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


class _FakeTorch:
    def __init__(self, *, cuda_available: bool, mps_available: bool) -> None:
        self.cuda = _FakeBackend(cuda_available)
        self.backends = type("Backends", (), {"mps": _FakeBackend(mps_available)})()

    @staticmethod
    def device(name: str) -> str:
        return name


def test_speecht5_auto_device_prefers_mps_when_cuda_unavailable() -> None:
    fake_torch = _FakeTorch(cuda_available=False, mps_available=True)
    resolved = SpeechT5Synthesizer._resolve_device(fake_torch, "auto")
    assert resolved == "mps"


def test_speecht5_explicit_mps_falls_back_to_cpu_when_unavailable() -> None:
    fake_torch = _FakeTorch(cuda_available=False, mps_available=False)
    resolved = SpeechT5Synthesizer._resolve_device(fake_torch, "mps")
    assert resolved == "cpu"
