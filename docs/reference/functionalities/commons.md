# Commons Circle Runtime

Status: implemented foundation with an explicit readiness audit

Commons is the shared Circle used by every domain-specific Circle. It owns the
reusable routing, policy, memory, observability, model-generation, and local
Satellite foundations that should not be reimplemented inside Life Admin,
Employment, Energy, Satcom, Medical, or a future startup Circle.

This page describes executable behavior, not aspiration. The canonical Galaxy
catalog defines what belongs to Commons; the readiness API separately reports
what works end to end today.

## Runtime flow

```text
User message
    ↓
Wormhole routing
    ↓
Commons policy + Mission Runtime
    ↓
selected Planet and Playbook
    ├── authorized local Satellite → validated deterministic result
    └── Mac Gemma Rogue Star       → probabilistic text generation
    ↓
response composer
    ↓
answer + source provenance + generation evidence + redacted trace
```

The composer never treats a successful HTTP model call as proof that the answer
is correct. It records whether model output was actually used, and exact
Satellite results take precedence over unverified base-model text.

## Readiness vocabulary

The implementation report uses four states:

| State | Meaning |
| --- | --- |
| `operational` | The active Control Room can execute the component end to end. |
| `partial` | A useful implementation exists, but a named dependency or workflow step is missing. |
| `declared` | The component is present in the canonical topology but has no executable runtime. |
| `disabled` | Code or a catalog entry exists, but the Chat boundary deliberately does not enable it. |

`catalog_status: active` is not an execution claim. Catalog status controls
topology and lifecycle; `runtime_status` records observed implementation
readiness.

## Current inventory

The running default Galaxy contains 30 non-Planet Commons components:

| Runtime state | Count | Components |
| --- | ---: | --- |
| Operational | 12 | Mission Runtime, Wormhole routing, Feature Architect, policy assessment, strict offline boundary, observability, working memory, long-term memory, Calculate, Unit Convert, Memory Write, Memory Search |
| Partial | 10 | Adversarial Review, Exploration Vault, knowledge search, summarization, claim verification, outbound approval, Personal Vault, Research with Provenance, Route & Synthesize, Scheduled Review |
| Declared | 4 | Artifact Store, calendar inspection, calendar proposals, Future Company Vault |
| Disabled | 4 | Gmail Fetch, Email Search, Email Summary, Email Classifier |

The counts are generated from a drift-checked matrix in
`easy_agents.constellation.commons`. If the canonical Commons membership
changes without a corresponding audit entry, the readiness builder fails
instead of silently reporting an incomplete picture.

## Response provenance

Every Wormhole Chat response has `answer_source`:

- `model`: generated model text was shown to the user.
- `satellite`: validated Satellite output is the answer; exact local Satellite
  requests do not invoke the model.
- `hybrid`: reserved for an explicitly implemented, evidence-preserving
  Satellite-plus-model synthesis path.
- `fallback`: no completed generation supplied the final answer.

When a language model is called, `generation` includes:

- a correlation-safe `generation_id`
- model identifier and completion state
- whether its text was used in the final answer
- finish reason and portable token counts when the adapter reports them
- measured runtime duration
- `accepted`, `degraded`, or `rejected` transport/output status
- the exact basic checks that fired

The basic checks detect empty or very short output, HTML markup, control
characters, prompt-prefix repetition, high repetition, and token-limit
truncation. They also check only a few explicit, mechanically testable format
constraints: requested brevity, a single requested item, and a requested count
of one to three sentences. They do **not** verify truth, general instruction
following, citations, or safety. Severely unusable or clearly noncompliant text
is marked `rejected`, excluded from the answer, and replaced with the Planet's
deterministic bounded plan. Mildly degraded output remains visible with its
warning. All model content remains advisory and unverified.

## Local Satellites

Four account-free Satellites execute through Chat today:

| Satellite | Typical request | Result source |
| --- | --- | --- |
| Calculate | `Calculate 12 * (3 + 4)` | validated arithmetic |
| Unit Convert | `Convert 5 miles to km` | validated unit conversion |
| Memory Write | `Remember that my grocery day is Saturday` | durable scoped record |
| Memory Search | `What do you remember about grocery day?` | scoped local retrieval |

Network access, email operations, notifications, calls, purchases, and other
external effects are not granted by ordinary chat text. Provider-backed
Satellites require explicit configuration and the approval workflow must be
made durable and resumable before they are enabled in Chat.

Exact local Satellite requests remain usable when Gemma is offline. Open-ended
advisory requests return HTTP 503 until the external Rogue Star is ready.

## HTTP APIs

Get the compact system readiness summary:

```bash
curl -sS http://127.0.0.1:8030/api/v2/readiness
```

Get the complete Commons component audit:

```bash
curl -sS http://127.0.0.1:8030/api/v2/circles/commons/readiness
```

The full response includes `summary`, runtime foundations, all component
states, evidence, limitations, and the next implementation priorities.

Send a conversational Mission:

```bash
curl -sS http://127.0.0.1:8030/api/v2/wormhole/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Help me plan my day"}'
```

Inspect `answer_source` and `generation.output_used` before attributing an
answer to Gemma. A `used_model` field means a model was called; it does not by
itself mean its text reached the final response.

## Adding a reusable Commons component

1. Decide whether the reusable unit is a capability, memory scope, Playbook,
   policy, Satellite, or service.
2. Add it to the typed catalog and attach it to the Commons Circle.
3. Implement the smallest shared runtime contract instead of embedding the
   behavior in one Planet.
4. Add an explicit entry to `_COMMONS_COMPONENTS` with evidence and a truthful
   runtime state. The drift check will fail until this is done.
5. For a Satellite, register it with the active `LocalSatelliteRuntime`; a
   catalog entry alone is not executable.
6. Add policy, authorization, failure, observability, and API tests.
7. Promote the state to `operational` only after the Control Room path works end
   to end.

## Known gaps and implementation order

The next Commons increments are intentionally ordered by reuse and safety:

1. a versioned local Artifact Store with retention and deletion controls
2. a durable scheduler for Scheduled Review wakeups and cancellation
3. source-backed knowledge ingestion, citations, and claim verification
4. durable approval decisions that can safely resume paused Missions
5. calendar adapters behind explicit account configuration and approval

Until those increments land, the readiness endpoint keeps them visible as
partial or declared rather than presenting the Galaxy as more capable than it
is.

## Verification

Run the focused Commons, Chat, Fleet, observability, model, and UI contracts:

```bash
.venv/bin/python -m pytest -q \
  tests/test_fleet_runtime.py \
  tests/test_wormhole_chat.py \
  tests/test_observability.py \
  tests/test_constellation_knowledge_graph.py \
  tests/test_mac_gemma.py
```

The suite covers all 30 audited components, model completion metadata,
degraded-output detection, final-answer attribution, authoritative Satellite
answers, redacted composition events, readiness APIs, and UI contracts.
