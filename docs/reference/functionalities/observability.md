# Realtime Monitoring and Tracing

Status: implemented local vertical slice

## What is implemented

The repository has one local-first observability pipeline for Fleet Missions and
existing graph trace events:

```text
runtime event
  -> normalize legacy shape when needed
  -> allowlist, bound, and redact
  -> append to SQLite
  -> update rebuildable projections
  -> publish to live browser subscribers
```

The pipeline provides:

- versioned `TraceEvent` contracts with Mission, Work order, Run, trace, span,
  actor, subject, status, severity, timing, and classification fields;
- central redaction before the event reaches storage or the browser;
- an append-only SQLite log with unique event IDs and monotonic sequences;
- durable Mission, Run, entity-activity, and alert projections;
- deterministic projection rebuilding after a restart;
- a bounded thread-safe fan-out hub;
- cursor-based history and replay APIs;
- Server-Sent Events with `Last-Event-ID` recovery;
- Map, Live, and Replay modes in the Constellation Control Room;
- live node states and agent-to-component activity edges;
- Mission lists, event inspection, filters, and a replay scrubber;
- deterministic alerts for failed, blocked, and approval-waiting Missions;
- a safe whole-fleet audit that traces every registered Specialist under one
  correlated Mission and returns a per-agent report.

The implementation lives in `src/easy_agents/observability/`. It uses the
standard-library `sqlite3` module and the existing FastAPI service; no external
telemetry service is required.

## Run the Control Room

```bash
./run/constellation.sh
```

Open `http://127.0.0.1:8030`, then select:

- **Map** for the stable Constellation topology;
- **Live** for current Mission and entity activity;
- **Replay** to reconstruct graph state from retained events.

Running a Sandbox mission from a Specialist inspector produces events. A local
API request does the same:

```bash
curl -X POST http://127.0.0.1:8030/api/missions/run \
  -H 'Content-Type: application/json' \
  -d '{
    "objective": "calculate a satellite RF link budget",
    "specialist_id": "rf_link_budget_specialist"
  }'
```

Select **Test all 70 agents** in Live mode to validate the complete compiled
fleet without model inference, network access, or external effects. The audit
emits the same Mission, Work-order, policy, Playbook, step, and Specialist
events as ordinary runs, so it also exercises persistence, projection, SSE,
and replay behavior.

By default, events are stored in `data/observability.db`. Override the location
before starting the server:

```bash
EASY_AGENTS_OBSERVABILITY_DB=/absolute/private/path/operations.db \
  ./run/constellation.sh
```

The database is runtime data and is ignored by Git.

## Event lifecycle

Fleet Runtime emits correlated events for:

- Mission creation, routing, start, terminal outcome, and failure;
- Work-order creation and terminal outcome;
- Specialist selection, start, completion, and failure;
- policy allow/block decisions and approval requests;
- Playbook and step lifecycle;
- local model start, completion, duration, and failure.

The shared legacy `TraceSink` adapter normalizes existing graph events such as
`turn_started`, `node_started`, `node_state`, `llm_call`, and `tool_call` into
the same event contract. It deliberately discards raw graph state, observations,
user input, responses, prompts, and tool payloads.

## Use it from an agent

`ObservabilityPipeline` implements the existing synchronous `TraceSink`
interface:

```python
from easy_agents.observability import ObservabilityPipeline

operations = ObservabilityPipeline.default()

# Existing GraphAgent-derived agents can receive it as trace_sink.
agent = MyGraphAgent(trace_sink=operations, ...)
```

Fleet Runtime accepts the richer recorder directly:

```python
from easy_agents.fleet import FleetRuntime, MissionRequest
from easy_agents.observability import ObservabilityPipeline

operations = ObservabilityPipeline.default()
fleet = FleetRuntime(event_recorder=operations)
result = fleet.run(MissionRequest(objective="Make a bounded daily plan."))
```

For tests or embedded use, avoid filesystem state:

```python
operations = ObservabilityPipeline.memory()
```

Custom runtime components should call `operations.record(...)` with operational
metadata only. Do not place prompts, responses, memory content, tool arguments,
credentials, or private reasoning in attributes.

## HTTP API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/operations/snapshot` | Current projections, recent events, stream health, and store health |
| `GET /api/events` | Cursor-based filtered history |
| `GET /api/events/stream` | SSE stream with durable catch-up |
| `GET /api/missions` | Recent Mission projections |
| `GET /api/missions/{id}` | One Mission and its Runs |
| `GET /api/missions/{id}/timeline` | Ordered replay events |
| `GET /api/runs/{id}` | One Run and its event list |
| `GET /api/metrics/summary` | Mission, Run, active-entity, alert, and stream counts |
| `POST /api/fleet/test` | Run every registered Specialist in one safe traced validation Mission |

Example history query:

```bash
curl 'http://127.0.0.1:8030/api/events?after_sequence=0&limit=100&severity=warning'
```

Example live stream:

```bash
curl -N 'http://127.0.0.1:8030/api/events/stream?after_sequence=0'
```

SSE frames use the durable sequence as `id` and the canonical event type as
`event`. A reconnect may provide `Last-Event-ID`; the server catches up from
SQLite before resuming live delivery.

## Privacy boundary

The central redactor runs before both persistence and fan-out. It:

- keeps only documented attribute names;
- removes raw prompt, response, user-input, state, observation, tool-payload,
  header, cookie, password, token, and memory-value fields;
- bounds strings, collections, and nesting depth;
- replaces common bearer, API-key, GitHub-token, and `sk-` secret patterns;
- sanitizes summaries, correlation identifiers, and entity references;
- publishes the exact object that was persisted.

The UI uses `textContent` for event content. The server binds to loopback by
default. Do not expose it on a network interface without authentication,
authorization, CSRF protection for future commands, and transport security.

No event is intended to contain chain-of-thought or hidden model reasoning.

## Failure and pressure behavior

- Events commit before live publication.
- Duplicate event IDs return the original committed event.
- Browser delivery is at least once; sequence-based reducers ignore duplicates.
- A subscriber registers before catch-up, preventing the snapshot-to-stream
  race from losing committed events.
- Each browser has a bounded queue. A browser that cannot keep up is
  disconnected and can recover from SQLite.
- A slow browser never blocks the agent thread.
- The UI retains its last state while reconnecting and marks the stream stale.

## Verification

Focused tests cover:

- secret redaction before storage and streaming;
- idempotent event IDs and monotonic sequence assignment;
- SQLite restart and deterministic projection rebuild;
- complete Fleet Mission correlation;
- complete 70-Specialist fleet validation with one Mission and distinct Runs;
- approval and model-failure visibility;
- snapshot, history, Mission, Run, replay, metric, and SSE contracts;
- legacy trace normalization without raw state leakage;
- bounded subscriber overflow and durable catch-up behavior;
- Constellation HTML/JavaScript contracts.

A synthetic in-memory load check appended 10,000 events across 100 Specialist
entities in 0.483 seconds, produced the operations snapshot in 1.748 ms, and
rebuilt projections from all events in 0.105 seconds on the development Mac.
This validates the local projection path, not end-to-end browser latency under
model workload.

Run them with:

```bash
.venv/bin/pytest -q \
  tests/test_observability.py \
  tests/test_fleet_runtime.py \
  tests/test_constellation_knowledge_graph.py
```

## Current constraints

- Fleet Runtime is fully wired; older standalone agents must still be given the
  pipeline as their `trace_sink`.
- Existing completed-only model/tool hooks cannot show a start event until that
  adapter is upgraded; Fleet model execution already emits start and terminal
  events.
- Approval decisions are visible, but approval records are not yet resumable
  and the dashboard intentionally has no approve/deny command path.
- Cancellation, retry, quarantine, retention scheduling, JSONL export, and
  OpenTelemetry export remain future control-plane work.
- Ordering is local to one SQLite service. Distributed workers need a later
  ingestion and ordering design.
- Metrics are current projection counts rather than long-window percentile
  aggregates.

See the [Realtime Monitoring and Tracing Plan](../../plans/realtime-monitoring-and-tracing-plan.md)
for the remaining hardening sequence.
