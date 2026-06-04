"""Speaker embedding loading utilities for local SpeechT5 voice synthesis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SpeakerEmbeddingSource:
    """Describes where a SpeechT5 speaker embedding should come from."""

    path: Path | None = None
    dataset_name: str | None = None
    dataset_split: str = "validation"
    dataset_index: int = 7306
    dataset_field: str = "xvector"


def _import_numpy() -> Any:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional runtime
        raise ModuleNotFoundError(
            "numpy is required for local SpeechT5 embeddings. "
            "Install the 'voice-local-tts' optional dependency."
        ) from exc
    return np


def _load_from_path(path: Path) -> Any:
    np = _import_numpy()
    if not path.exists():
        raise FileNotFoundError(f"Speaker embedding file not found: {path}")
    embedding = np.load(path)
    if getattr(embedding, "ndim", 0) == 1:
        embedding = embedding.reshape(1, -1)
    return embedding.astype("float32")


def _load_from_dataset(source: SpeakerEmbeddingSource) -> Any:
    np = _import_numpy()
    try:
        from datasets import load_dataset
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional runtime
        raise ModuleNotFoundError(
            "datasets is required to load SpeechT5 speaker embeddings from Hugging Face. "
            "Install the 'voice-local-tts' optional dependency."
        ) from exc

    if not source.dataset_name:
        raise ValueError("dataset_name is required when loading a speaker embedding from Hugging Face.")
    dataset = load_dataset(source.dataset_name, split=source.dataset_split)
    row = dataset[int(source.dataset_index)]
    if source.dataset_field not in row:
        raise KeyError(
            f"Speaker embedding field '{source.dataset_field}' was not found in dataset {source.dataset_name}."
        )
    embedding = np.asarray(row[source.dataset_field], dtype="float32")
    if embedding.ndim == 1:
        embedding = embedding.reshape(1, -1)
    return embedding


def load_speaker_embedding(source: SpeakerEmbeddingSource | None) -> Any | None:
    """Loads a speaker embedding from either a local `.npy` file or a Hugging Face dataset."""

    if source is None:
        return None
    if source.path is not None:
        return _load_from_path(source.path)
    if source.dataset_name:
        return _load_from_dataset(source)
    return None


def save_speaker_embedding_from_hf_dataset(
    *,
    output_path: Path,
    dataset_name: str = "Matthijs/cmu-arctic-xvectors",
    dataset_split: str = "validation",
    dataset_index: int = 7306,
    dataset_field: str = "xvector",
) -> Path:
    """Downloads an embedding from a Hugging Face dataset and saves it as `.npy`."""

    np = _import_numpy()
    source = SpeakerEmbeddingSource(
        dataset_name=dataset_name,
        dataset_split=dataset_split,
        dataset_index=dataset_index,
        dataset_field=dataset_field,
    )
    embedding = _load_from_dataset(source)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(output_path, embedding)
    return output_path


def save_speaker_embedding_from_audio(
    *,
    input_path: Path,
    output_path: Path,
    device: str | None = None,
    sample_rate: int = 16000,
) -> Path:
    """Computes a speaker embedding from a reference audio sample and saves it as `.npy`."""

    np = _import_numpy()
    try:
        import torch
        import torchaudio
        from speechbrain.inference.speaker import EncoderClassifier
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional runtime
        raise ModuleNotFoundError(
            "speechbrain, torch, and torchaudio are required to derive a speaker embedding from audio. "
            "Install the 'voice-local-tts' optional dependency."
        ) from exc

    if not input_path.exists():
        raise FileNotFoundError(f"Reference audio file not found: {input_path}")

    wav, sr = torchaudio.load(str(input_path))
    if wav.ndim > 1 and wav.size(0) > 1:
        wav = wav.mean(dim=0, keepdim=True)
    if sr != sample_rate:
        wav = torchaudio.functional.resample(wav, orig_freq=sr, new_freq=sample_rate)
    wav = wav / (wav.abs().max() + 1e-9)
    mono = wav.squeeze(0)
    chosen_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    encoder = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-xvect-voxceleb",
        run_opts={"device": chosen_device},
    )
    batch = mono.unsqueeze(0).to(chosen_device)
    with torch.no_grad():
        embedding = encoder.encode_batch(batch).squeeze().cpu().numpy().astype(np.float32)
    if embedding.ndim == 1:
        embedding = embedding.reshape(1, -1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(output_path, embedding)
    return output_path
