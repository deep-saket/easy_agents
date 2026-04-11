"""Created: 2026-04-10

Purpose: Exposes reusable retrieval and vector-index components.
"""

from src.retrieval.faiss_backend import FaissVectorBackend
from src.retrieval.hash_embedding import HashEmbeddingProvider
from src.retrieval.hybrid import merge_retrieval_hits
from src.retrieval.models import IndexedItem, RetrievalHit
from src.retrieval.sentence_transformer_embedding import SentenceTransformerEmbeddingProvider
from src.retrieval.vector_backend import EmbeddingProvider, VectorRetrievalBackend

__all__ = [
    "EmbeddingProvider",
    "FaissVectorBackend",
    "HashEmbeddingProvider",
    "IndexedItem",
    "RetrievalHit",
    "SentenceTransformerEmbeddingProvider",
    "VectorRetrievalBackend",
    "merge_retrieval_hits",
]
