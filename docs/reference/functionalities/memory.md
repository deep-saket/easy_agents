# Memory and Retrieval

Status: verified for the tested local backends and retrieval contracts.

## Working Memory

Two working-memory implementations are in active use:

- `WorkingMemory`: a lightweight Pydantic object with recent messages and a state dictionary.
- `ConversationMemory`: a repository-backed session object loaded through `SessionStore`.

Both expose the node-facing operations `add_user_message`, `add_agent_message`, and `set_state`.

Use `WorkingMemory` for a small single-process agent. Use `ConversationMemory` when messages and control state must survive object recreation through a repository such as DuckDB.

## Typed Long-Term Memory

The repository defines these typed records:

| Type | Intended use |
| --- | --- |
| Semantic | Facts and reusable knowledge |
| Episodic | Past events and interactions |
| Procedural | Reusable processes or successful action patterns |
| Task | Work that should be resumed or monitored |
| Reflection | Post-run assessment and lessons |
| Error | Failures and recovery context |

Typed records apply type-specific defaults and remain queryable by type.

## Storage Layers

- **Hot:** bounded in-process cache for fast access.
- **Warm:** DuckDB persistence and filtered search.
- **Cold:** JSONL/archive persistence for older records.

`MemoryStore` normalizes scope and metadata, persists normal records to warm storage, optionally caches them hot, archives old warm records to cold storage, and rehydrates cold records when retrieved by ID.

## Minimal Persistent Store

```python
from pathlib import Path

from src.memory.layers import ColdMemoryLayer, HotMemoryLayer, WarmMemoryLayer
from src.memory.store import MemoryStore
from src.memory.types import SemanticMemory

root = Path("agents/runtime/memory/my_agent")
store = MemoryStore(
    hot_layer=HotMemoryLayer(max_items=64),
    warm_layer=WarmMemoryLayer(root / "memory.duckdb"),
    cold_layer=ColdMemoryLayer(root / "archive.jsonl"),
    default_scope="agent_local",
    agent_id="my_agent",
)

stored = SemanticMemory(
    content={"fact": "The user prefers concise summaries."},
    metadata={"tags": ["preference"]},
).store_warm(store)

results = store.search("concise summaries", filters={"type": "semantic"})
```

Use a temporary or explicitly chosen runtime path during development. Memory may contain personal data; define redaction and retention before using it with real users.

## Retrieval

The memory system supports:

- scope and agent filtering
- type, tag, source, and source-ID filters
- created-before and created-after filters
- layered retrieval and cold-record rehydration
- retrying query candidates
- local-to-global escalation through `MemoryRouter` and `MemoryService`
- optional vector indexing and hybrid keyword/vector retrieval
- priority-ordered sleeping tasks

Vector retrieval requires the relevant optional dependency or a custom backend. Tests use a deterministic hash embedding and in-memory vector backend, so passing tests do not prove quality of a production embedding model.

## Verification

Thirteen focused storage/type/vector tests passed. They cover DuckDB and JSONL persistence, archival, rehydration, scope-aware service escalation, hot caching, time filters, sleeping-task priority, typed record round trips, indexing, and hybrid result merging.

Nine additional node tests passed for state-configured retrieval targets, query candidates, typed writes, and LLM-assisted memory decisions.

## Constraints

- There is no single default persistence topology; concrete agents wire stores manually.
- Hot memory is process-local and disappears on restart.
- JSONL writes are local file operations, not a concurrent distributed store.
- Long-term retention, encryption, deletion, and user-consent policies are application responsibilities.
- Global-memory escalation must be explicitly allowed in `RetrievalContext`.

See [Memory Architecture](../../architecture/memory-architecture.md) for the deeper design.
