# Conversation Journals and Reviews

Status: implemented local runtime

The exploration journal preserves what the user and Galaxy discussed so future
reviews can identify themes, decisions, opportunities, and useful next work.
The complete turn is saved before Chat responds; Gemma tags it afterward as a
background task. It is not a replacement for working history or explicit Vault
memory.

## Three distinct memory surfaces

| Surface | Purpose | Persistence | How content enters |
| --- | --- | --- | --- |
| Chat history | Recent context supplied to the next answer | bounded SQLite, 20 turns and 128 conversations | every successful turn |
| Exploration journal | Complete auditable conversation plus semantic analysis | one formatted JSON document per conversation | every successful Control Room turn |
| Vault memory | Durable fact intentionally available for later retrieval | typed Commons SQLite records scoped by Vault | explicit model-selected `memory_write` |

Keeping these surfaces separate matters. Chat continuity does not silently
become long-term memory, while the journal remains reviewable without granting
every Planet semantic-memory authority.

## Storage layout

The standalone Control Room writes:

```text
data/
├── galaxy_chat.db
├── commons.db
└── conversation_journals/
    └── chat-<identifier>.json
```

Each JSON file has this stable shape:

```json
{
  "version": 1,
  "conversation_id": "chat-...",
  "galaxy_id": "personal",
  "created_at": "...",
  "updated_at": "...",
  "turns": [
    {
      "message_id": "message-...",
      "mission_id": "mission-...",
      "user_message": "...",
      "assistant_message": "...",
      "vault_id": "exploration",
      "duration_ms": 12345.678,
      "circle_ids": ["venture_exploration"],
      "planet_ids": ["opportunity_portfolio_steward"],
      "invoked_satellite_ids": [],
      "answer_source": "model",
      "analysis_status": "captured",
      "analysis": {
        "analysis_id": "analysis-...",
        "summary": "...",
        "primary_intent": "...",
        "topics": [],
        "tags": [],
        "user_goals": [],
        "named_entities": [],
        "facts_to_remember": [],
        "decisions": [],
        "opportunities": [],
        "constraints_or_risks": [],
        "open_questions": [],
        "suggested_follow_ups": [],
        "relevance": "strategic",
        "sensitivity": "ordinary"
      },
      "analysis_error": null
    }
  ],
  "latest_review": null
}
```

Writes use a temporary sibling followed by an atomic replace. The response first
contains a `pending` journal receipt and the UI polls while Gemma analyzes the
saved turn. The complete turn is retained even when semantic generation fails;
in that case the turn has
`analysis_status: pending`, an empty `analysis`, and a bounded diagnostic.

## What is model-driven

Gemma generates every semantic field and every cross-turn review. Validation
code checks the returned Pydantic schema and allows one corrected model attempt.
There is no keyword tagger, regex classifier, or deterministic semantic
fallback. Code is responsible only for technical metadata, bounds, validation,
authorization, and persistence.

The review schema includes:

- summary and recurring themes;
- direction of travel;
- decisions and commitments;
- promising opportunities;
- unresolved questions;
- recommended next steps;
- knowledge worth preserving.

## HTTP API

| Method | Path | Result |
| --- | --- | --- |
| `GET` | `/api/v2/wormhole/journals` | newest-first list of complete journals |
| `GET` | `/api/v2/wormhole/conversations/{id}/journal` | one complete journal |
| `POST` | `/api/v2/wormhole/conversations/{id}/review` | generate, persist, and return a Gemma review |
| `DELETE` | `/api/v2/wormhole/conversations/{id}/journal` | explicitly delete one journal |

Starting a new Chat clears the bounded context but intentionally preserves its
journal. Journal deletion is separate and explicit so exploration history is
not lost accidentally.

## Privacy and operations

Journal files contain raw conversation text and can therefore contain private
or sensitive information. Keep the server on loopback, protect the local data
directory with operating-system permissions and backups appropriate to the
content, and delete a journal explicitly when it should no longer be retained.
The sensitivity label is a model-generated review aid, not a security control.

## Reuse from Python

```python
from pathlib import Path

from easy_agents.constellation import ConversationJournal

journal = ConversationJournal(
    Path("data/conversation_journals"),
    llm=my_local_gemma_client,
    galaxy_id="personal",
)

record = journal.get("chat-example")
review = journal.review("chat-example")
```

The LLM client must expose
`structured_generate(prompt, schema, **generation_options)` and accept the
bounded `max_tokens` override used by analysis and review. If it does not,
technical capture remains available and semantic analysis stays pending with a
bounded diagnostic in `analysis_error`.
