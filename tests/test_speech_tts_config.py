from __future__ import annotations

from pathlib import Path

import numpy as np

from speech.embedding_loader import SpeakerEmbeddingSource, load_speaker_embedding
from speech.speecht5_tts import SpeechT5TTSConfig


def test_speecht5_config_resolves_relative_embedding_path(tmp_path: Path) -> None:
    config = SpeechT5TTSConfig.from_mapping(
        {
            "speaker_embedding_path": "runtime/voice/tts_speaker_embedding.npy",
            "device": "cpu",
        },
        base_dir=tmp_path,
    )
    assert config.speaker_embedding_path == (tmp_path / "runtime/voice/tts_speaker_embedding.npy").resolve()


def test_load_speaker_embedding_from_local_path(tmp_path: Path) -> None:
    embedding_path = tmp_path / "speaker.npy"
    np.save(embedding_path, np.asarray([0.1, 0.2, 0.3], dtype=np.float32))
    loaded = load_speaker_embedding(SpeakerEmbeddingSource(path=embedding_path))
    assert loaded is not None
    assert loaded.shape == (1, 3)
    assert loaded.dtype == np.float32
