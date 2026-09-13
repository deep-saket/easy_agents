# Agent Runtime and Reusable Nodes

Status: verified for the tested synchronous, in-process contracts.

## `BaseAgent`

`src/agents/base_agent.py` defines the smallest shared runtime contract:

- optional `llm`
- stable `agent_name`
- structured logger
- optional `trace_sink`
- abstract `run(user_input, session_id)` method

It intentionally does not prescribe graph topology, tool ownership, storage, or a universal return model. Concrete agents commonly return a string, while several specialists return dictionaries.

## `GraphAgent`

`src/agents/graph_agent.py` is the reusable graph runtime. One turn:

1. loads conversation memory through `SessionStore`
2. stores the user message
3. invokes memory retrieval
4. plans with `ReactNode`
5. optionally executes and reflects on a tool call
6. builds a response
7. stores the agent response
8. emits trace events

The compiled default graph is fixed inside `GraphAgent`. An agent that needs another topology currently assembles its own `StateGraph`, as MailMind and Collection Agent do.

## Shared State

`AgentState` is a `TypedDict` shared by framework nodes. Common keys include:

- identity: `session_id`, `turn_id`, `trigger_type`
- input/output: `user_input`, `response`
- working context: `memory`, `memory_context`, `intent`, `decision`
- tool loop: `observation`, `observations`, `pending_tool_calls`, `steps`
- routing: `route`, `final`, `waiting`
- diagnostics: `error`, `trace`, prompt and model fields emitted by nodes

The current state also includes Collection Agent fields. New domain-neutral agents should use only the keys they need and keep new business-specific state inside their own package until state extension is standardized.

## Individual Nodes

| Node | Function | Important behavior |
| --- | --- | --- |
| `IntentNode` | Classifies user intent | Supports JSON model output, deterministic defaults, keyword fallbacks, response maps, and route maps |
| `ReactNode` | Selects a tool call or direct response | Supports pre/post hooks, queued calls, a maximum step count, and optional deterministic fallback |
| `ToolExecutionNode` | Executes the selected tool | Uses `ToolExecutor` and appends a normalized observation |
| `MemoryRetrieveNode` | Loads working or long-term memory context | Accepts constructor- or state-provided memory targets and query candidates |
| `MemoryNode` | Applies working-memory and typed long-term updates | Can use explicit updates or an LLM-assisted selection path |
| `ReflectNode` | Checks whether work is complete | Can loop with feedback and emit reflection memory updates |
| `ResponseNode` | Produces final response text | Uses a precomputed response, observation template, or LLM |
| `RouterNode` | Selects a named route | Delegates to any object implementing `route(user_input=..., state=...)` |
| `ApprovalNode` | Queues an approval item | Does nothing when no queue or item is supplied; policy remains caller-owned |
| `WhatsAppNode` | Sends through a WhatsApp adapter | Can continue immediately or mark the graph as waiting for a reply |
| `AgentNode` | Invokes another agent | Derives a child session ID and returns the result as an observation or response |

Every reusable node implements `execute(state) -> partial update`. Nodes with conditional behavior also expose `route(state) -> label`.

## Agent Composition

Any object with an `agent_name` and compatible `run()` method can be nested:

```python
from src.nodes import AgentNode

delegate_node = AgentNode(
    agent=my_agent,
    input_template="{user_input}",
    session_id_template="{session_id}::delegate::{agent_name}",
    include_as_observation=True,
)
```

Composition is currently synchronous and in-process. There is no generic discovery registry, durable handoff protocol, process isolation, or centralized timeout/budget enforcement.

## Verification

This focused suite passed:

```text
16 passed
```

It covers agent delegation, intent parsing/fallback, ReAct hooks, reflection, memory read/write nodes, and state-provided memory targets. Additional smoke checks passed for:

- `GraphAgent` with an in-memory session repository and no model
- turn-start, node, and turn-finish trace events
- `ApprovalNode` queue handoff
- `RouterNode` route selection

Use [Create an Agent](../../guides/create-an-agent.md) for a complete working graph example.
