# Chat with Your Galaxy

Status: implemented local, model-planned runtime

The Control Room Chat is the Wormhole entry point to the Personal Agent
Galaxy. Every natural-language message is interpreted by the external local
Gemma service. Gemma selects a Circle, an accountable Planet, and one to five
typed actions. The application validates that plan against schemas and the
Planet Charter before executing anything.

There is no keyword, regular-expression, or lexical intent router in this Chat
path, and there is no deterministic intent fallback. Deterministic code is
limited to safety-critical validation, authorization, storage, exact tools,
and formatting verified results.

## Start Chat

Mac Gemma is hosted by the separate Foundation Mac Serving repository:

```bash
cd /Users/saketm10/Projects/foundation-ai-platform/mac-serving
.venv/bin/mac-serve serve
```

Then start this repository's Control Room:

```bash
cd /Users/saketm10/Projects/openclaw_agents
./run/constellation.sh
```

Open `http://127.0.0.1:8030`, choose **Chat**, select a Vault, enter a message,
and press Enter or **Send through Wormhole**. Shift+Enter inserts a new line.

## How one message runs

```text
Chat Portal
    ↓
Gemma action planner
    ├── selects Circle
    ├── selects accountable Planet
    └── selects 1–5 typed actions
    ↓
Schema + Planet Charter + Vault validation
    ↓
Wormhole → Galaxy → selected Circle → selected Planet
    ↓
Authorized local actions and Satellites
    ↓
Gemma synthesis with verified local results
    ↓
Answer + plan evidence + action results + correlated trace
```

Constellations remain connected-graph context; they are not route hops.
Satellites are tools, not agents. Mac Gemma is a Rogue Star outside Galaxy
ownership and can be reused by multiple Galaxies.

## Natural-language behavior matrix

| User intent | Model action | Accountable example | Local effect |
| --- | --- | --- | --- |
| Ask, brainstorm, plan, or analyze | `respond` | domain Planet | advisory answer |
| Exact arithmetic | `calculate` | Personal Steward | validated local calculation |
| Convert units | `unit_convert` | Personal Steward | validated local conversion |
| Explicitly retain a fact | `memory_write` | Personal Steward | write selected Vault |
| Recall retained information | `memory_search` | Personal Steward | search selected Vault |
| Create a document or memo | `artifact_create` | Digital Librarian | immutable artifact version |
| Inspect artifacts | `artifact_list` | Digital Librarian | local artifact listing |
| Add supplied evidence | `knowledge_add` | Knowledge Librarian | local cited source |
| Search evidence | `knowledge_search` | Knowledge Librarian | ranked cited hits |
| Summarize evidence | `knowledge_summarize` | Knowledge Librarian | extractive cited summary |
| Check claims against sources | `knowledge_verify` | Knowledge Librarian | lexical support assessment |
| Schedule a follow-up review | `review_create` | Safety Steward | durable local wakeup |
| Inspect reviews | `review_list` | Safety Steward | local review listing |
| Propose a calendar item | `calendar_propose` | Schedule Coordinator | local-only proposal |
| Inspect the local calendar | `calendar_list` | Schedule Coordinator | local projection |
| Inspect approval records | `approval_list` | approval-gated Planet | local approval listing |
| Record a human approval decision | `approval_decide` | approval-gated Planet | decision only; no protected effect |
| Inspect shared runtime health | `commons_status` | Safety Steward | Commons status and counts |

A message may request several related local actions. For example, “Remember
that the satcom idea uses optical links and schedule a review” can produce a
`memory_write` plus `review_create` plan. One Planet must have authority for
every action. Plans are bounded to five actions and execute in listed order.

Calls, emails, messages, purchases, payments, notifications, and provider
calendar changes are intentionally absent from the action allow-list. Gemma
may offer advisory help, but ordinary prose cannot trigger those effects.

## What was broken and why

The previous path recognized a few phrases with regexes and keywords. That
created five practical failures:

1. Paraphrases could miss the intended operation.
2. A message could execute only one action.
3. Commons artifacts, knowledge, reviews, calendar, and approvals were not
   reachable from Chat even though their APIs worked.
4. Circle and Planet routing could still be selected by lexical overlap.
5. Tool-shaped messages bypassed Gemma, so behavior appeared deterministic
   when the model service was unavailable.

The new planner makes both routing and action choices through Gemma. Invalid
JSON, argument schemas, Circle membership, or Charter authority cause a second
model attempt with bounded error feedback. If the second plan is still
invalid, the API fails visibly; code does not guess or repair the intent.

Memory retrieval also now ranks non-adjacent query-term overlap inside exactly
one selected Vault, so “Sunday call” can retrieve “Sunday evening call.” This
is bounded retrieval after the model selected `memory_search`, not intent
classification.

## Conversations, Vaults, and verified output

The server retains at most 20 turns per conversation and 128 conversations.
The normal launcher stores bounded history in `data/galaxy_chat.db`.
Conversation history is not durable semantic memory.

An explicit model-selected `memory_write` stores a record in one of
`working`, `long_term`, `personal`, `employer_authorized`, `exploration`, or
the inactive-by-default `future_company` Vault. Search never crosses the
selected Vault. The selected Planet must declare both the memory Satellite and
that Vault.

Exact local results are rendered before model commentary. If answer generation
is rejected but a local action completed, Chat returns only verified action
evidence. If neither usable generation nor an action result exists, Chat fails;
it does not emit a canned fallback.

## HTTP contract

```bash
curl -sS http://127.0.0.1:8030/api/v2/wormhole/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Remember that sample 42 is the control and schedule a review for 2030-10-03T09:00:00+05:30","vault_id":"exploration"}'
```

Pass the returned `conversation_id` to continue the same conversation. The
response contains:

- the answer and canonical `Trajectory`;
- `planning` evidence with model, attempt count, selected Circle and Planet,
  action names, and duration;
- `action_invocations` for every completed local action;
- compatibility `satellite_invocations` for the four tool-backed actions;
- generation quality/provenance evidence;
- a visualization route for Map highlighting.

Runtime readiness at `/api/v2/readiness` publishes the complete supported
action list and explicitly reports `deterministic_intent_fallback: false`.

## Failure behavior

- Gemma unavailable: HTTP 503 for every natural-language Chat request.
- Model cannot produce an authorized plan after two attempts: HTTP 502.
- Invalid user input, failed local action, or unusable answer with no verified
  result: HTTP 400.
- External effects remain disabled even after a local approval record is
  approved; a separate authenticated provider worker would be required.
- Planning, model generation, Satellite execution, and response composition
  produce correlated operational events without storing message content in
  trace attributes.

The server should remain loopback-only until authentication, per-principal
Galaxy authorization, and request-rate controls are implemented.

## Verification

```bash
.venv/bin/python -m pytest -q \
  tests/test_natural_language_chat.py \
  tests/test_wormhole_chat.py \
  tests/test_commons_runtime.py
node --check endpoints/static/constellation/app.js
```

The behavior matrix covers all 18 actions, multi-action execution, Charter
rejection with model-only retry, no offline rule fallback, durable memory,
live plan evidence, API serialization, and observability.
