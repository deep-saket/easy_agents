"""Created: 2026-04-01

Purpose: Exposes the layered local memory retriever through the legacy import.
"""

from src.memory.retrieval.retriever import LayeredMemoryRetriever as MemoryRetriever

__all__ = ["MemoryRetriever"]
