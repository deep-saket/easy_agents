# Collection Agent Runtime

This directory stores generated runtime artifacts for `agents/collection_agent`.

## Generation Lifecycle

| Source Component | Files it creates/updates | When |
| --- | --- | --- |
| `CollectionRepository` | `conversation_messages.json`, `conversation_states.json`, `tool_logs.json` | On agent startup and every turn |
| `CollectionDataStore` | `contact_attempts.json`, `verification_attempts.json`, `payment_links.json`, `promises.json`, `followups.json`, `dispositions.json`, `escalations.json`, `channel_switches.json`, `phone_payments.json`, `plan_proposals.json` | On startup (ensures files) and during tool execution |
| `CollectionAgent._persist_trace` | `traces/<timestamp>_<trace_id>.json`, `traces/latest_trace.json` | After each completed turn |
| `JSONLTraceSink` (optional) | `traces/events.jsonl` (or configured path) | Real-time during node/tool/llm events |

## File Reference

### Session and turn state

| File | Type | Purpose |
| --- | --- | --- |
| `conversation_messages.json` | object (`session_id -> [messages]`) | Conversation history by session |
| `conversation_states.json` | object (`session_id -> state`) | Working state (`mode`, `active_case_id`, `current_plan`, etc.) |
| `tool_logs.json` | array | Tool executor audit entries (input/output/status/error/timestamp) |

### Tool runtime artifacts

| File | Type | Written by tools |
| --- | --- | --- |
| `contact_attempts.json` | array | `contact_attempt` |
| `verification_attempts.json` | array | `customer_verify` |
| `payment_links.json` | array | `payment_link_create`, `payment_status_check` |
| `promises.json` | array | `promise_capture` |
| `followups.json` | array | `followup_schedule` |
| `dispositions.json` | array | `disposition_update` |
| `escalations.json` | array | `human_escalation` |
| `channel_switches.json` | array | `channel_switch` |
| `phone_payments.json` | array | `pay_by_phone_collect` |
| `plan_proposals.json` | array | `plan_propose` |

### Trace outputs

| File/Path | Type | Purpose |
| --- | --- | --- |
| `traces/<timestamp>_<trace_id>.json` | JSON object | Full per-turn trace snapshot (node order, tool order, timings, llm calls) |
| `traces/latest_trace.json` | JSON object | Last completed turn trace |
| `traces/events.jsonl` | JSONL | Event stream (`turn_started`, `node_started`, `tool_call`, `llm_call`, etc.) |

## Reading Traversal Order

- Node order: `summary.node_hits` in trace JSON.
- Tool order: `tool_calls[].tool_name` in trace JSON.
- Real-time event order: line order in `events.jsonl`.

## Reset for Clean Demo

To reset runtime files before a demo:

- Object files: set to `{}`
  - `conversation_messages.json`
  - `conversation_states.json`
- Array files: set to `[]`
  - all other top-level JSON files in this directory
- Trace files: optional cleanup
  - remove files inside `runtime/traces/`

Do not reset files while an interactive run is active.
