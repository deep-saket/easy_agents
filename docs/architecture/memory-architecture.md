# Memory Architecture

## Core Principle

All memory is stored in JSON or databases.
Markdown is not used for storage.

Reason:

- JSON is indexable
- JSON is structured
- JSON supports querying and filtering
- it is compatible with SQLite, DuckDB, vector DBs, and search engines

## Memory Taxonomy

### Semantic Memory

Stable knowledge.

Examples:

- user preferences
- important entities
- learned rules

### Episodic Memory

Past interactions.

Examples:

- emails processed
- tool outputs
- decisions

### Procedural Memory

Not stored as ordinary runtime data.

Exists as:

- tools
- planners
- prompts

### Working Memory

In-memory only.

Examples:

- current conversation
- temporary state

## Storage Layers

### Hot Memory

- in-memory cache
- recent data
- fast access

### Warm Memory

- primary indexed database layer
- main query layer

### Cold Memory

- archived JSON files
- slow retrieval
- rehydrated when needed

## Memory Schema

All memory follows a structured schema with fields such as:

- `id`
- `type`
- `layer`
- `content`
- `metadata`
- `created_at`

## Retrieval Flow

1. classify query
2. search hot memory
3. search warm memory
4. fallback to cold memory
5. rank by relevance, recency, and priority

## Storage Flow

1. agent generates output
2. extract important data
3. convert to a structured memory item
4. store in warm memory
5. optionally cache in hot memory
6. index immediately

## Error Memory

Purpose:

- avoid repeated failures
- improve planning

## Reflection Memory

Stores:

- reasoning
- improvements
- analysis

## Sleeping Memory

Deferred task queue stored in JSON or a database.

Examples:

- summarization
- cleanup
- re-indexing

## Design Principles

- JSON-only storage
- strongly typed memory
- multi-layer storage
- query-first design
- agent-agnostic memory
- scalable to vector DBs

## Related

- [Memory Vector Index Plan](../plans/memory-vector-index-plan.md)
