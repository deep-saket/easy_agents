"""Local SpeechT5 text-to-speech synthesizer with optional speaker embeddings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .embedding_loader import SpeakerEmbeddingSource, load_speaker_embedding


@dataclass(slots=True)
class SpeechT5TTSConfig:
    """Configuration for a local SpeechT5 synthesis backend."""

    model_name: str = "microsoft/speecht5_tts"
    vocoder_name: str = "microsoft/speecht5_hifigan"
    model_sample_rate: int = 16000
    device: str = "cpu"
    speaker_embedding_path: Path | None = None
    speaker_embedding_dataset: str | None = "Matthijs/cmu-arctic-xvectors"
    speaker_embedding_split: str = "validation"
    speaker_embedding_index: int = 7306
    speaker_embedding_field: str = "xvector"

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None, *, base_dir: Path | None = None) -> "SpeechT5TTSConfig":
        data = dict(payload or {})
        embedding_path = data.get("speaker_embedding_path")
        resolved_path: Path | None = None
        if isinstance(embedding_path, str) and embedding_path.strip():
            path = Path(embedding_path.strip())
            if not path.is_absolute() and base_dir is not None:
                path = (base_dir / path).resolve()
            resolved_path = path
        return cls(
            model_name=str(data.get("model_name", "microsoft/speecht5_tts")),
            vocoder_name=str(data.get("vocoder_name", "microsoft/speecht5_hifigan")),
            model_sample_rate=int(data.get("model_sample_rate", 16000)),
            device=str(data.get("device", "cpu")),
            speaker_embedding_path=resolved_path,
            speaker_embedding_dataset=(
                str(data["speaker_embedding_dataset"]).strip()
                if data.get("speaker_embedding_dataset") is not None
                else None
            ),
            speaker_embedding_split=str(data.get("speaker_embedding_split", "validation")),
            speaker_embedding_index=int(data.get("speaker_embedding_index", 7306)),
            speaker_embedding_field=str(data.get("speaker_embedding_field", "xvector")),
        )

    def speaker_embedding_source(self) -> SpeakerEmbeddingSource | None:
        if self.speaker_embedding_path is None and not self.speaker_embedding_dataset:
            return None
        return SpeakerEmbeddingSource(
            path=self.speaker_embedding_path,
            dataset_name=self.speaker_embedding_dataset,
            dataset_split=self.speaker_embedding_split,
            dataset_index=self.speaker_embedding_index,
            dataset_field=self.speaker_embedding_field,
        )


class SpeechT5Synthesizer:
    """Wraps the Hugging Face SpeechT5 stack for local synthesis."""

    def __init__(self, config: SpeechT5TTSConfig) -> None:
        self.config = config
        try:
            import torch
            from transformers import SpeechT5ForTextToSpeech, SpeechT5HifiGan, SpeechT5Processor
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional runtime
            raise ModuleNotFoundError(
                "transformers and torch are required for local SpeechT5 synthesis. "
                "Install the 'voice-local-tts' optional dependency."
            ) from exc

        self._torch = torch
        self.device = self._resolve_device(torch, config.device)
        self.processor = SpeechT5Processor.from_pretrained(config.model_name)
        self.model = SpeechT5ForTextToSpeech.from_pretrained(config.model_name).to(self.device)
        self.vocoder = SpeechT5HifiGan.from_pretrained(config.vocoder_name).to(self.device)
        self._speaker_embedding = None

    @staticmethod
    def _resolve_device(torch: Any, requested: str) -> Any:
        normalized = str(requested or "auto").strip().lower()
        if normalized in {"auto", ""}:
            if torch.cuda.is_available():
                return torch.device("cuda")
            mps_backend = getattr(torch.backends, "mps", None)
            if mps_backend is not None and mps_backend.is_available():
                return torch.device("mps")
            return torch.device("cpu")
        if normalized == "cuda":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if normalized == "mps":
            mps_backend = getattr(torch.backends, "mps", None)
            if mps_backend is not None and mps_backend.is_available():
                return torch.device("mps")
            return torch.device("cpu")
        return torch.device("cpu")

    def _speaker_embedding_tensor(self) -> Any | None:
        if self._speaker_embedding is not None:
            return self._speaker_embedding
        embedding = load_speaker_embedding(self.config.speaker_embedding_source())
        if embedding is None:
            self._speaker_embedding = None
            return None
        tensor = self._torch.from_numpy(embedding).to(self.device).float()
        if tensor.dim() == 1:
            tensor = tensor.unsqueeze(0)
        self._speaker_embedding = tensor
        return tensor

    def synthesize(self, text: str) -> Any:
        """Returns a mono float32 waveform at the model sample rate."""

        if not text.strip():
            raise ValueError("SpeechT5Synthesizer requires non-empty text.")
        inputs = self.processor(text=[text], return_tensors="pt").to(self.device)
        speaker_embedding = self._speaker_embedding_tensor()
        with self._torch.no_grad():
            audio = self.model.generate_speech(
                inputs["input_ids"],
                speaker_embeddings=speaker_embedding,
                vocoder=self.vocoder,
            )
        waveform = audio.detach().cpu().numpy().astype("float32").reshape(-1)
        return waveform
