# Observability

Status: smoke verified; no dedicated observability regression suite.

## Structured Logging

`BaseAgent` exposes `log_info`, `log_debug`, `log_warning`, and `log_exception`. Context is rendered as key-value data through `StructuredLogger`.

Logs can contain user inputs, state, tool arguments, and provider errors. Treat log storage as sensitive and avoid recording credentials, OAuth tokens, raw financial data, or unnecessary personal information.

## Execution Traces

`ExecutionTrace` records one agent turn:

- trace, agent, and session identifiers
- start/finish times and status
- ordered node spans
- model calls and token fields when known
- tool calls, durations, status, and errors
- aggregate summary counts

Context-local helpers associate nested events with the active turn and node:

- `trace_turn()`
- `trace_node()`
- `record_llm_call()`
- `record_tool_call()`
- `emit_trace_event()`

## Trace Sinks

- `StdoutJSONTraceSink` emits one JSON object per stdout line.
- `JSONLTraceSink` appends one JSON object per line to a configured file.
- Any object implementing `emit(event)` can be used as a custom sink.

Collection Agent adds readable summaries and per-turn trace output. Conversation Manager maintains a separate JSONL delivery/runtime log because it wraps rather than lives inside the collection graph.

## Minimal Custom Sink

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RecordingSink:
    events: list[dict[str, Any]] = field(default_factory=list)

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)
```

Pass the instance as `trace_sink` when constructing an agent.

## Verification

An in-memory smoke ran `GraphAgent` without a model and confirmed this event lifecycle:

```text
turn_started -> node_started/node_finished ... -> turn_finished
```

The smoke also verified the completed fallback response. Tool and model trace hooks are exercised indirectly by agent, tool, and model tests.

## Constraints

- There is no cross-agent run database or unified operations dashboard.
- Token counts may be unknown for adapters that do not report usage.
- JSONL appends do not provide retention, rotation, encryption, or concurrent distributed ingestion.
- Redaction is not centralized.
- Conversation Manager and graph traces use related but separate event models.
