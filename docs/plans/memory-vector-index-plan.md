# Memory Vector Index Plan

This document describes how to add FAISS-based memory indexing and retrieval as a feature, while keeping the index backend replaceable with alternatives such as ChromaDB later.

It also defines the indexing and retrieval contracts so the same system can be reused later by a generic RAG node.

## Goal

Add semantic similarity search to the memory system without coupling memory storage to one vector database.

Required outcomes:

- keep `MemoryStore`, `MemoryService`, and `MemoryRouter` usable with the current DuckDB plus JSONL storage
- add vector indexing as a separate feature layer
- support hybrid retrieval:
  - structured filters
  - keyword search
  - embedding similarity
- make FAISS the first index backend
- make ChromaDB swappable later without changing callers
- make the retrieval contracts reusable for both memory retrieval and future document RAG retrieval

## Non-Goals

- replacing DuckDB warm storage
- moving all memory to a vector DB
- removing keyword or metadata retrieval
- changing the memory taxonomy
- implementing the full RAG node in this phase

## Design Principle

Separate:

- memory storage backend
- vector index backend
- embedding provider
- retrieval abstraction

The storage backend and the similarity index must not depend on each other directly.

## Architecture

Recommended split:

- reusable vector contracts in `src/retrieval/`
- memory-specific orchestration in `src/memory/`

This keeps the vector backend reusable for a future RAG node.

## Proposed Modules

- `src/retrieval/vector_backend.py`
- `src/retrieval/models.py`
- `src/memory/index/base.py`
- `src/memory/index/faiss_backend.py`
- `src/memory/index/chroma_backend.py`
- `src/memory/index/indexer.py`
- `src/memory/retrieval/hybrid_retriever.py`

## Implementation Direction

Start with:

- FAISS
- normalized cosine similarity
- file-backed local index
- rebuildable index state from warm storage

Then add:

- incremental indexing
- better index variants
- swappable ChromaDB backend
- reuse in document retrieval / RAG
