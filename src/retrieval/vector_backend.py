"""Created: 2026-04-10

Purpose: Defines backend-agnostic vector retrieval contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.retrieval.models import IndexedItem, RetrievalHit


class EmbeddingProvider(ABC):
    """Defines the contract for text embedding providers."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Returns the embedding dimension produced by this provider."""
        raise NotImplementedError

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Embeds one text input into a fixed-size vector."""
        raise NotImplementedError

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embeds multiple texts using the single-text API by default."""
        return [self.embed_text(text) for text in texts]


class VectorRetrievalBackend(ABC):
    """Defines the contract for similarity index backends."""

    @abstractmethod
    def upsert(self, item: IndexedItem) -> None:
        """Creates or replaces one indexed item."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, item_id: str) -> None:
        """Deletes one indexed item if present."""
        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        vector: list[float],
        filters: dict[str, object] | None = None,
        limit: int = 20,
    ) -> list[RetrievalHit]:
        """Returns the best-matching indexed items for the given vector."""
        raise NotImplementedError

    @abstractmethod
    def rebuild(self, items: list[IndexedItem]) -> None:
        """Replaces the full index contents from a list of indexed items."""
        raise NotImplementedError


__all__ = ["EmbeddingProvider", "VectorRetrievalBackend"]
