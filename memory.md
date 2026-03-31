# Memory Architecture (JSON-First Design)

## Core Principle

All memory MUST be stored in JSON or databases.
Markdown is NOT used for storage.

Reason:
- JSON is indexable
- JSON is structured
- JSON supports querying and filtering
- Compatible with SQLite, vector DBs, and search engines

---

# 1. Memory Taxonomy

## 1.1 Semantic Memory
Stable knowledge.

Stored as JSON records.

Examples:
- user preferences
- important entities
- learned rules

---

## 1.2 Episodic Memory
Past interactions.

Stored as structured JSON logs.

Examples:
- emails processed
- tool outputs
- decisions

---

## 1.3 Procedural Memory
NOT stored as data.

Exists as:
- tools
- planners
- prompts

---

## 1.4 Working Memory
In-memory only.

Examples:
- current conversation
- temporary state

---

# 2. Storage Layers

## 2.1 Hot Memory
- in-memory cache
- recent data
- fast access

## 2.2 Warm Memory (PRIMARY)
- SQLite database
- indexed
- main query layer

## 2.3 Cold Memory
- JSON files (compressed or archived)
- slow retrieval
- rehydrated when needed

---

# 3. Memory Schema

All memory follows:

{
  "id": "uuid",
  "type": "semantic | episodic | error | reflection | task",
  "layer": "hot | warm | cold",
  "content": "string or structured data",
  "metadata": {
    "agent": "mailmind",
    "tags": [],
    "source": "tool/user/system",
    "priority": "low|medium|high"
  },
  "created_at": "timestamp"
}

---

# 4. Indexing

## Warm Layer (SQLite)

Indexes:
- content (FTS)
- type
- timestamp
- tags
- agent

Optional:
- embeddings

---

## Cold Layer

- No indexing by default
- Optional batch indexing on access

---

# 5. Retrieval Flow

1. Classify query
2. Search hot memory
3. Search warm memory (primary)
4. Fallback to cold memory
5. Rank results:
   - relevance
   - recency
   - priority

---

# 6. Storage Flow

1. Agent generates output
2. Extract important data
3. Convert to JSON MemoryItem
4. Store in:
   - SQLite (warm)
   - optional cache (hot)
5. Index immediately

---

# 7. Error Memory

Stores:

{
  "input": "...",
  "output": "...",
  "error_type": "user_feedback | reflection | tool_failure",
  "correction": "...",
  "root_cause": "...",
  "agent": "..."
}

Purpose:
- avoid repeated failures
- improve planning

---

# 8. Reflection Memory

Stores:
- reasoning
- improvements
- analysis

---

# 9. Sleeping Memory (Deferred Tasks)

Queue stored in JSON or DB.

Examples:
- summarization
- cleanup
- re-indexing

Executed asynchronously.

---

# 10. OpenClaw Comparison (Architectural)

OpenClaw:
- uses Markdown (MEMORY.md)
- human-readable
- not optimized for indexing

This system:
- JSON-first
- DB-backed
- query-first architecture

OpenClaw indexing:
- keyword + embedding
- implicit structure

This system:
- explicit schema
- strict typing
- better query performance

---

# 11. Design Principles

- JSON-only storage
- strongly typed memory
- multi-layer storage
- query-first design
- agent-agnostic memory
- scalable to vector DB

---

# Summary

This architecture combines:

- structured JSON memory
- SQLite indexing
- hot/warm/cold layers
- error + reflection learning
- future scalability

Result:
A scalable, indexable, production-grade memory system.
