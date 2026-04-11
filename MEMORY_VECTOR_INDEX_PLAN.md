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
  - source of truth for records
  - currently DuckDB plus JSONL
- vector index backend
  - similarity search only
  - first implementation: FAISS
  - future option: ChromaDB
- embedding provider
  - computes vectors
  - OpenAI, local sentence-transformer, or other provider
- retrieval abstraction
  - reusable across memory items and future RAG documents/chunks

The storage backend and the similarity index must not depend on each other directly.

## Target Architecture

### 1. New Concepts

Add three abstractions:

- `EmbeddingProvider`
  - `embed_text(text: str) -> list[float]`
  - `embed_texts(texts: list[str]) -> list[list[float]]`
- `MemoryIndexBackend`
  - `upsert(record_id: str, vector: list[float], metadata: dict[str, object]) -> None`
  - `delete(record_id: str) -> None`
  - `search(vector: list[float], filters: dict[str, object] | None, limit: int) -> list[IndexSearchHit]`
  - `rebuild(items: list[IndexableMemoryRecord]) -> None`
- `MemoryIndexer`
  - orchestrates embedding generation and writes to the selected index backend

Add one more abstraction above memory-specific retrieval:

- `VectorRetrievalBackend`
  - generic similarity interface used by memory retrieval and future RAG retrieval

### 2. Retrieval Split

Retrieval should become two-stage:

1. candidate retrieval
   - from warm storage using existing filters
   - `scope`, `agent_id`, `type`, `tags`, `source_type`, `source_id`
2. ranking
   - keyword score
   - recency
   - importance
   - confidence
   - similarity score

This should be hybrid retrieval, not vector-only retrieval.

### 3. Storage Contract

Warm storage remains the source of truth for memory records.

The vector index stores:

- `record_id`
- embedding vector
- minimal filterable metadata
  - `scope`
  - `agent_id`
  - `type`
  - `layer`
  - `tags`

If the vector index is lost, it must be rebuildable from warm storage.

## Proposed Modules

Add these modules under `src/memory/`:

- `src/memory/embeddings/base.py`
- `src/memory/embeddings/openai_provider.py`
- `src/memory/embeddings/sentence_transformer_provider.py`
- `src/memory/index/base.py`
- `src/memory/index/faiss_backend.py`
- `src/memory/index/chroma_backend.py`
- `src/memory/index/models.py`
- `src/memory/index/indexer.py`
- `src/memory/retrieval/hybrid_retriever.py`

Possible supporting config:

- `src/memory/config.py`
  - or extend existing config if preferred

Add reusable vector modules under `src/retrieval/` or `src/vector/`:

- `src/retrieval/vector_backend.py`
- `src/retrieval/models.py`
- `src/retrieval/hybrid.py`

Recommended direction:

- put backend-agnostic vector contracts in `src/retrieval/`
- keep memory-specific orchestration in `src/memory/`

That way a future RAG node can depend on `src/retrieval/` directly instead of reaching into `src/memory/`.

## Interface Plan

### `IndexSearchHit`

This should be a small model, for example:

```python
class IndexSearchHit(BaseModel):
    record_id: str
    similarity: float
    metadata: dict[str, object] = Field(default_factory=dict)
```

### `IndexableMemoryRecord`

This should normalize what gets embedded:

```python
class IndexableMemoryRecord(BaseModel):
    record_id: str
    text: str
    metadata: dict[str, object]
```

Do not embed raw `MemoryRecord` directly inside the backend interface.

### Generic Retrieval Result

To support future RAG reuse, also define a generic retrieval result model independent of memory:

```python
class RetrievalHit(BaseModel):
    item_id: str
    score: float
    text: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
```

Memory retrieval can adapt this into `MemoryRecord`.
Future RAG retrieval can adapt this into document chunks.

## Data Model Changes

### `MemoryRecord`

Do not make storage depend on embeddings to function.

Optional additions:

- `embedding_model: str | None = None`
- `embedding_updated_at: datetime | None = None`

Do not store the full vector directly on `MemoryRecord` unless there is a strong debugging need.

Reason:

- vectors can be large
- FAISS does not need vectors inside the main record row
- Chroma can store vectors separately

If debugging visibility is needed, store vectors in a separate warm table, not as a primary field on `MemoryRecord`.

### Warm Store Schema

Add one new optional table in DuckDB:

- `memory_index_state`
  - `record_id`
  - `embedding_model`
  - `indexed_at`
  - `content_hash`

Purpose:

- know whether a record needs reindexing
- enable deterministic rebuilds

This table should not be treated as the vector index itself.

## FAISS Implementation Plan

### Phase 1: Local File-Based FAISS Index

Use FAISS as a local artifact stored on disk.

Suggested persistence layout:

- `data/memory_index/faiss.index`
- `data/memory_index/id_map.json`
- `data/memory_index/meta.json`

The FAISS backend should manage:

- vector dimension validation
- id-to-row mapping
- on-disk save/load
- full rebuild

Recommended FAISS mode for v1:

- cosine similarity via normalized vectors
- `IndexFlatIP` as the simplest starting point

Reason:

- straightforward
- no training step
- good enough until scale requires IVF/HNSW/PQ

### Phase 2: Incremental Upsert/Delete

If delete semantics become awkward with plain FAISS, wrap with:

- `IndexIDMap2`

or rebuild periodically if simplicity is more important than perfect in-place mutation.

For v1, correctness is more important than mutation efficiency.

## ChromaDB Compatibility Plan

The caller-facing code must depend only on the abstract backend contracts.

That means:

- `HybridMemoryRetriever` calls `MemoryIndexBackend.search(...)`
- `MemoryIndexer` calls `MemoryIndexBackend.upsert(...)`
- future `RAGRetriever` calls `VectorRetrievalBackend.search(...)`
- `MemoryStore` never imports `faiss` or `chromadb`
- future document stores should also never import `faiss` or `chromadb`

When switching to ChromaDB later:

- implement `ChromaMemoryIndexBackend`
- keep the same `MemoryIndexBackend` interface
- reuse the same embedding provider contract
- keep the same retrieval flow

The rest of the memory system should not change.

The future RAG node should only need:

- a document store
- a chunking pipeline
- an adapter from document chunks to `VectorRetrievalBackend`

The vector backend itself should remain shared.

## Retrieval Flow Plan

### Current

- warm search by keyword and filters
- optional cold fallback
- recency-based ranking

### Target

1. embed the query
2. retrieve vector candidates from the index backend
3. retrieve keyword candidates from warm storage
4. merge by `record_id`
5. load full records from warm store
6. score with hybrid ranking
7. fallback to cold if needed

Future RAG retrieval should use the same first three steps:

1. embed the query
2. retrieve vector candidates from the shared vector backend
3. load full chunks/documents from its source store
4. optionally rerank
5. return grounded context to the node

### Hybrid Ranking

Update ranking to something like:

```text
final_score =
  0.45 * similarity_score +
  0.20 * keyword_score +
  0.15 * recency_score +
  0.10 * importance_score +
  0.10 * confidence_score
```

These weights should be config-driven, not hardcoded permanently.

## Write Path Plan

When a memory record is added:

1. store it in warm storage as usual
2. derive indexable text
3. compute content hash
4. check whether indexing is needed
5. enqueue or execute indexing
6. write/update index state

For v1, indexing can be synchronous behind a feature flag.

For v2, move indexing to a sleeping task:

- `task_type = "memory_reindex"`

That fits the existing sleeping queue model.

## Feature Flag Plan

Add explicit memory retrieval config:

- `memory_similarity_enabled: bool`
- `memory_similarity_backend: Literal["none", "faiss", "chroma"]`
- `memory_embedding_provider: Literal["openai", "sentence_transformer"]`
- `memory_embedding_model: str`
- `memory_hybrid_search_enabled: bool`
- `memory_vector_top_k: int`

Add backend-neutral retrieval config that can be shared with RAG later:

- `vector_backend: Literal["none", "faiss", "chroma"]`
- `embedding_provider: Literal["openai", "sentence_transformer"]`
- `embedding_model: str`

Memory-specific config can wrap or override these if needed.

Required behavior:

- if disabled, current retrieval path remains unchanged
- if enabled, hybrid retrieval is used
- if vector backend fails, system falls back to keyword retrieval and logs the failure

## Implementation Phases

### Phase 0: Prep

- define interfaces
- add config
- add index models
- add content extraction helper for index text

Acceptance:

- no behavior change
- current tests still pass

### Phase 1: FAISS Backend

- implement `FaissMemoryIndexBackend`
- implement local file persistence
- implement rebuild from warm store

Acceptance:

- index can build from existing warm records
- vector search returns record ids and similarity scores

### Phase 2: Embedding Providers

- implement one hosted provider
- implement one local provider
- add embedding dimension validation

Acceptance:

- query and record embeddings are consistent
- failures are surfaced clearly

### Phase 3: Hybrid Retriever

- implement `HybridMemoryRetriever`
- merge keyword and vector candidates
- update ranking

Acceptance:

- semantically similar queries retrieve relevant records even without exact keyword overlap
- metadata filters still apply

### Phase 4: Incremental Indexing

- add indexing during writes
- add rebuild CLI or notebook workflow
- integrate sleeping task support for deferred reindex

Acceptance:

- new records become searchable by similarity
- rebuild restores index after deletion or corruption

### Phase 5: Chroma Backend

- implement `ChromaMemoryIndexBackend`
- reuse same interface and tests

Acceptance:

- backend swap requires config change only

## Testing Plan

Add tests for:

- embedding provider contract
- FAISS index save/load
- id mapping persistence
- hybrid retrieval merge and ranking
- filtered similarity retrieval
- rebuild from warm store
- fallback to keyword retrieval on vector failure
- backend swap contract using shared backend test suite

Also add contract tests for reusable retrieval abstractions:

- one backend test suite that both FAISS and Chroma implementations must pass
- one generic retrieval-hit contract test not tied to memory records

Add one notebook demo similar to the memory system demo:

- seed semantic and episodic records
- compare keyword-only vs hybrid retrieval
- show exact-match miss but semantic hit

Later add a second notebook:

- document chunk indexing demo
- retrieval from the same backend contract
- simple prompt assembly for a future RAG node

## Migration Plan

### Step 1

Ship interfaces plus config with retrieval disabled by default.

### Step 2

Implement FAISS and local embedding provider behind the feature flag.

### Step 3

Add notebook/demo validation.

### Step 4

Enable for semantic memory first.

Reason:

- semantic memory benefits most from similarity search
- episodic memory can stay mostly keyword plus recency initially

### Step 5

Expand to episodic, reflection, and error memory once scoring is tuned.

### Step 6

Reuse the same vector backend contracts for document chunks and build a RAG node on top.

That future RAG node should not introduce a separate vector system.

## Risks

### 1. Coupling storage and index

Avoid putting FAISS-specific logic inside DuckDB storage classes.

### 2. Filter mismatch

Vector hits must still respect `scope`, `agent_id`, and `type`.

### 3. Silent staleness

If memory content changes, the corresponding index entry must be refreshed.

### 4. Overweight similarity

Pure similarity search can bury recent critical items.

Use hybrid scoring.

### 5. Backend lock-in

Do not expose FAISS-specific types outside the backend implementation.

## Recommended First Slice

Implement this exact slice first:

1. `EmbeddingProvider`
2. `VectorRetrievalBackend`
3. `MemoryIndexBackend`
4. `FaissMemoryIndexBackend`
5. `MemoryIndexer`
6. `HybridMemoryRetriever`
7. feature flag off by default
8. semantic-memory-only indexing in notebook/demo

This gets the architecture right before scaling scope.

## Success Criteria

The feature is complete when:

- similarity retrieval works for semantic memory
- metadata filtering still works
- warm storage remains the source of truth
- FAISS can be rebuilt from warm storage
- switching to Chroma requires only a backend implementation and config change
- disabling the feature cleanly returns to current keyword retrieval
- the same vector backend contract can be reused later by a RAG node without redesign
