"""Created: 2026-04-10

Purpose: Provides a lightweight deterministic embedding provider for testing and local demos.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

from src.retrieval.vector_backend import EmbeddingProvider


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


@dataclass(slots=True)
class HashEmbeddingProvider(EmbeddingProvider):
    """Embeds text into a deterministic hashed bag-of-words vector."""

    _dimension: int = 64

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


__all__ = ["HashEmbeddingProvider"]
