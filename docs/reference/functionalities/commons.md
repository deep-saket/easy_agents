# Commons Circle Runtime

Status: implemented local runtime; provider effects remain disabled

Commons is the shared Circle used by every domain Circle. It provides reusable
state and safety services so individual Planets do not invent incompatible
memory, artifact, knowledge, scheduling, calendar, or approval implementations.

The Control Room exposes these services in the **Commons** tab. The same typed
contracts are available under `/api/v2/commons` and through
`CommonsRuntime`. With the normal launcher, all state is stored in
`data/commons.db`.

## What works now

The default Galaxy has 30 non-Planet Commons components. Runtime readiness is:

| Runtime state | Count | Notes |
| --- | ---: | --- |
| Operational | 23 | Routing, policy, observability, local Satellites, named Vaults, artifacts, local knowledge, review scheduling, approval records, and calendar proposals |
| Partial | 3 | Adversarial Review, Research with Provenance, and multi-Planet Route & Synthesize |
| Declared | 0 | Every declared Commons component has an implementation or an explicit disabled boundary |
| Disabled | 4 | Gmail Fetch, Email Search, Email Summary, and Email Classifier are not enabled in Wormhole Chat |

`catalog_status` describes topology and lifecycle. It is not an execution
claim. `/api/v2/circles/commons/readiness` derives the runtime totals from the
active local capabilities and fails if the catalog and audit drift apart.

## Architecture

```text
Wormhole Chat ──┐
Control Room ───┼── CommonsRuntime ─── SQLite (commons.db)
Typed API ──────┘       ├── named Vault memories
                        ├── immutable artifact versions
                        ├── local knowledge sources + citations
                        ├── scheduled review wakeups
                        ├── approval decisions + resume context
                        └── local calendar proposals
```

The state runtime is deliberately local and predictable: validation, storage,
exact calculations, and authorized effects do not depend on model guesses. In
Wormhole Chat, however, natural-language intent, Circle selection, Planet
selection, and action selection are all performed by Gemma. There is no
deterministic intent router or fallback. An approved record is evidence of a
human decision; it is not permission for this module to send an email, place
an order, make a call, or modify an external calendar.

## Named Vaults

The runtime creates six explicit data boundaries:

| Vault | Intended use | Default state |
| --- | --- | --- |
| `working` | temporary task and conversation support | active |
| `long_term` | durable cross-session facts | active |
| `personal` | private life, household, and preference memory | active |
| `employer_authorized` | information allowed inside the employment boundary | active |
| `exploration` | scientific and startup-opportunity exploration | active |
| `future_company` | future-company material after an explicit lifecycle decision | inactive |

Writes and searches always name exactly one Vault. Chat defaults to `personal`;
the selector in the Chat composer changes the boundary when Gemma selects a
memory write or search. The planner selects a Planet whose Charter includes
both the Memory Satellite and the requested Vault. There is no phrase matcher
and no cross-Vault fallback.

The Commons tab can write, search, export, and delete individual records. The
API also supports a destructive whole-Vault purge, but only when the request
contains the exact confirmation string `delete <vault_id>`.

```bash
# Store and search one personal fact
curl -sS http://127.0.0.1:8030/api/v2/commons/vaults/personal/memories \
  -H 'Content-Type: application/json' \
  -d '{"content":"Mom prefers a Sunday call","tags":["family"]}'

curl -sS 'http://127.0.0.1:8030/api/v2/commons/vaults/personal/memories?query=Sunday'

# Export without creating another server-side file
curl -sS http://127.0.0.1:8030/api/v2/commons/vaults/personal/export
```

Conversation history remains separate. `data/galaxy_chat.db` contains bounded
recent turns; `data/commons.db` contains memories that the user explicitly
asked to retain.

## Artifact Store

`POST /api/v2/commons/artifacts` creates an artifact. Supplying the returned
`artifact_id` again creates the next immutable version. Every version has a
SHA-256 checksum, timestamp, kind, metadata, and content. Deletion is soft:
normal reads hide deleted versions while `include_deleted=true` retains an
audit/recovery view.

```bash
curl -sS http://127.0.0.1:8030/api/v2/commons/artifacts \
  -H 'Content-Type: application/json' \
  -d '{"name":"Energy opportunity memo","kind":"memo","content":"First thesis"}'
```

## Local knowledge and citations

Knowledge ingestion accepts text explicitly supplied by the caller. Each
source receives a stable `source-...` identifier and content checksum. Search
is bounded lexical retrieval. Summaries are deterministic excerpts prefixed
with citation identifiers.

Claim verification reports lexical coverage as `supported`, `partial`, or
`unsupported`. This is evidence triage, not semantic proof, fact checking, or
a substitute for reviewing the cited source.

```bash
curl -sS http://127.0.0.1:8030/api/v2/commons/knowledge/sources \
  -H 'Content-Type: application/json' \
  -d '{"title":"Battery note","content":"Sodium-ion cells avoid lithium."}'

curl -sS 'http://127.0.0.1:8030/api/v2/commons/knowledge/summary?query=sodium'
```

## Scheduled Reviews

Scheduled Reviews are persisted with a due time, optional payload, and optional
recurrence in days. The app lifespan runs a one-second local monitor that
atomically moves elapsed records from `scheduled` to `due` and emits a redacted
event. `POST /api/v2/commons/reviews/claim-due` exposes the same transition for
workers and deterministic tests.

Completing a recurring review advances its due time and returns it to
`scheduled`; cancelling it is terminal. Becoming due does not execute the
payload as a Mission.

## Approval records

Approval records persist the Mission, protected effects, rationale, and bounded
`resume_context`. A human can decide a pending record exactly once. The context
can later be consumed by a provider-specific worker, but this local runtime does
not implement that worker and never auto-resumes an effect.

This separation is intentional:

```text
request effect → persist pending approval → human decision → approved record
                                                        └─ no external action here
```

## Calendar proposals

Calendar APIs create, inspect, approve, reject, or cancel local proposals. They
do not connect to Google Calendar, Outlook, or the operating system calendar.
Approved local items appear in the Commons calendar projection and can later be
consumed by an explicitly configured provider adapter.

## API map

| Area | Endpoints |
| --- | --- |
| Runtime | `GET /api/v2/commons/summary` |
| Vaults | `GET/PATCH /vaults`, `POST/GET /vaults/{id}/memories`, export, record delete, confirmed purge |
| Artifacts | `POST/GET /artifacts`, `GET/DELETE /artifacts/{id}` |
| Knowledge | source ingest/get/delete, search, extractive summary, claim verification |
| Reviews | create/list, claim due, complete/cancel |
| Approvals | create/list, approve/reject/cancel |
| Calendar | propose/list, approve/reject/cancel |

All paths in the table are relative to `/api/v2/commons`.

## Response provenance and local Satellites

Wormhole Chat distinguishes `model`, `satellite`, and `hybrid` answers. Gemma
plans every request first. Calculate, Unit Convert, Memory Write, and Memory
Search execute locally through Charter and Satellite authorization; the other
Commons services execute through the same validated action boundary. Exact
local results take precedence over unverified model continuation. There is no
canned or deterministic answer fallback.

Those checks detect transport and obvious formatting failures; they do not
prove truth, citation quality, or general instruction following.

## Using the runtime from Python

```python
from pathlib import Path

from easy_agents.constellation.commons_runtime import (
    ArtifactCreate,
    CommonsRuntime,
    VaultMemoryCreate,
)

commons = CommonsRuntime(db_path=Path("data/my_galaxy_commons.db"))
commons.add_memory(
    "exploration",
    VaultMemoryCreate(content="Investigate sodium-ion storage economics"),
)
memo = commons.create_artifact(
    ArtifactCreate(name="Storage thesis", content="Initial evidence map")
)
commons.create_artifact(
    ArtifactCreate(
        artifact_id=memo.artifact_id,
        name=memo.name,
        content="Revised evidence map",
    )
)
commons.close()
```

Use one `CommonsRuntime` per Galaxy process and inject that same instance into
the API and local Satellite runtime. This ensures UI operations and Planet tool
calls enforce the same persistence and Vault boundary.

## Remaining boundaries

- Adversarial Review still needs rubric-specific evaluators.
- Research with Provenance has local sources and citations but no approved
  primary-source connector.
- Route & Synthesize exists in Fleet, but Chat still routes one Planet per
  message.
- Provider-backed calendar, email, call, purchase, and notification effects
  require authentication, per-principal authorization, idempotency, and an
  explicit post-approval worker.
- The server should remain loopback-only until authentication, rate limits, and
  per-user Galaxy authorization are implemented.

See the [Commons Completion Plan](../../plans/commons-completion-plan.md) for the
remaining sequence.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_commons_runtime.py \
  tests/test_wormhole_chat.py tests/test_natural_language_chat.py
node --check endpoints/static/constellation/app.js
```

The tests cover every model-planned Chat action plus persistence and Vault isolation, exact-confirmation purge,
artifact versioning and deletion, stable knowledge citations, lexical claim
labels, recurring review transitions, approval decisions, calendar proposals,
the complete API, multi-action requests, invalid-plan retries without a rule
fallback, and Chat/API use of the same selected Vault.
