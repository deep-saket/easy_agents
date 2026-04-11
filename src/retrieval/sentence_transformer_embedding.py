"""Created: 2026-04-10

Purpose: Provides a sentence-transformers embedding provider for reusable retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.retrieval.vector_backend import EmbeddingProvider


@dataclass(slots=True)
class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Embeds text using a local sentence-transformers model."""

    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    normalize_embeddings: bool = True
    _model: Any = field(default=None, init=False, repr=False)
    _dimension: int | None = field(default=None, init=False, repr=False)

    @property
    def dimension(self) -> int:
        self._ensure_model()
        if self._dimension is None:
            sample = self.embed_text("dimension probe")
            self._dimension = len(sample)
        return self._dimension

    def embed_text(self, text: str) -> list[float]:
        self._ensure_model()
        vector = self._model.encode(
            text,
            normalize_embeddings=self.normalize_embeddings,
        )
        values = vector.tolist() if hasattr(vector, "tolist") else list(vector)
        if self._dimension is None:
            self._dimension = len(values)
        return [float(value) for value in values]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self._ensure_model()
        matrix = self._model.encode(
            texts,
            normalize_embeddings=self.normalize_embeddings,
        )
        rows = matrix.tolist() if hasattr(matrix, "tolist") else [list(row) for row in matrix]
        vectors = [[float(value) for value in row] for row in rows]
        if vectors and self._dimension is None:
            self._dimension = len(vectors[0])
        return vectors

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Sentence-transformers embeddings require optional dependencies. "
                "Install with `pip install -e \".[memory-vector-local]\"`."
            ) from exc
        self._model = SentenceTransformer(self.model_name)


__all__ = ["SentenceTransformerEmbeddingProvider"]
