"""Created: 2026-04-10

Purpose: Implements a FAISS-backed reusable vector index backend.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.retrieval.models import IndexedItem, RetrievalHit
from src.retrieval.vector_backend import VectorRetrievalBackend


def _normalize(vector: list[float]) -> list[float]:
    norm = sum(value * value for value in vector) ** 0.5
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _metadata_matches(metadata: dict[str, Any], filters: dict[str, object] | None) -> bool:
    if not filters:
        return True
    for key, expected in filters.items():
        actual = metadata.get(key)
        if key == "tags":
            expected_tags = [expected] if isinstance(expected, str) else list(expected) if isinstance(expected, list) else []
            actual_tags = actual if isinstance(actual, list) else []
            if not all(tag in actual_tags for tag in expected_tags):
                return False
            continue
        if isinstance(expected, dict):
            actual_dict = actual if isinstance(actual, dict) else {}
            for nested_key, nested_expected in expected.items():
                if actual_dict.get(nested_key) != nested_expected:
                    return False
            continue
        if actual != expected:
            return False
    return True


@dataclass(slots=True)
class FaissVectorBackend(VectorRetrievalBackend):
    """Stores vectors in a local FAISS index with JSON metadata sidecars."""

    index_path: Path
    state_path: Path | None = None
    dimension: int | None = None
    search_multiplier: int = 5
    _items: dict[str, IndexedItem] = field(default_factory=dict, init=False, repr=False)
    _id_order: list[str] = field(default_factory=list, init=False, repr=False)
    _faiss: Any = field(default=None, init=False, repr=False)
    _np: Any = field(default=None, init=False, repr=False)
    _index_obj: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_path or self.index_path.with_suffix(".json")
        self._load_dependencies()
        self._load_state()
        self._rebuild_index()

    def upsert(self, item: IndexedItem) -> None:
        self._validate_dimension(item.vector)
        self._items[item.item_id] = item.model_copy(update={"vector": _normalize(item.vector)})
        self._persist_all()

    def delete(self, item_id: str) -> None:
        if item_id in self._items:
            del self._items[item_id]
            self._persist_all()

    def search(
        self,
        vector: list[float],
        filters: dict[str, object] | None = None,
        limit: int = 20,
    ) -> list[RetrievalHit]:
        if not self._items:
            return []
        self._validate_dimension(vector)
        normalized = _normalize(vector)
        query = self._np.array([normalized], dtype="float32")
        top_k = min(max(limit * self.search_multiplier, limit), len(self._id_order))
        scores, indexes = self._index.search(query, top_k)
        hits: list[RetrievalHit] = []
        for score, raw_index in zip(scores[0], indexes[0], strict=False):
            if raw_index < 0 or raw_index >= len(self._id_order):
                continue
            item = self._items[self._id_order[int(raw_index)]]
            if not _metadata_matches(item.metadata, filters):
                continue
            hits.append(RetrievalHit(item_id=item.item_id, score=float(score), text=item.text, metadata=item.metadata))
            if len(hits) >= limit:
                break
        return hits

    def rebuild(self, items: list[IndexedItem]) -> None:
        self._items = {}
        for item in items:
            self._validate_dimension(item.vector)
            self._items[item.item_id] = item.model_copy(update={"vector": _normalize(item.vector)})
        self._persist_all()

    @property
    def _index(self) -> Any:
        if self._faiss is None:
            raise RuntimeError("FAISS dependencies are not available.")
        if self._index_obj is None:
            self._rebuild_index()
        return self._index_obj

    def _load_dependencies(self) -> None:
        try:
            import faiss  # type: ignore
            import numpy as np
        except ImportError as exc:
            raise RuntimeError(
                "FAISS vector retrieval requires optional dependencies. Install with `pip install -e \".[memory-vector]\"`."
            ) from exc
        self._faiss = faiss
        self._np = np

    def _load_state(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        items = payload.get("items", [])
        self.dimension = payload.get("dimension", self.dimension)
        self._items = {item["item_id"]: IndexedItem.model_validate(item) for item in items}

    def _persist_all(self) -> None:
        self._rebuild_index()
        if self.state_path is None:
            return
        payload = {
            "dimension": self.dimension,
            "items": [item.model_dump(mode="json") for item in self._items.values()],
        }
        self.state_path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
        self._faiss.write_index(self._index, str(self.index_path))

    def _rebuild_index(self) -> None:
        if self.dimension is None:
            self.dimension = next((len(item.vector) for item in self._items.values()), None)
        if self.dimension is None:
            self._index_obj = self._faiss.IndexFlatIP(1)
            self._id_order = []
            return
        self._id_order = list(self._items)
        index = self._faiss.IndexFlatIP(self.dimension)
        if self._id_order:
            matrix = self._np.array([self._items[item_id].vector for item_id in self._id_order], dtype="float32")
            index.add(matrix)
        self._index_obj = index

    def _validate_dimension(self, vector: list[float]) -> None:
        if self.dimension is None:
            self.dimension = len(vector)
            return
        if len(vector) != self.dimension:
            raise ValueError(f"Vector dimension mismatch: expected {self.dimension}, got {len(vector)}")


__all__ = ["FaissVectorBackend"]
