# Multi-Agent Platform

This repository is a shared multi-agent platform.

`MailMind` is the first concrete agent built on top of it. It is not the platform itself.

The shared reusable platform code lives under [`src/`](src).
Concrete agents live under [`agents/`](agents).

## Current Split

Belongs in `src/`:

- LLM abstractions and factories
- tool abstractions, registry, executor, schemas
- planner abstractions and reusable ReAct planning
- memory and session-store logic
- storage and logging abstractions
- common schemas, ids, config helpers, interfaces
- reusable ReAct agent runtime

Belongs in `agents/mailmind/`:

- email policies
- email-specific prompts
- MailMind config wrapper
- MailMind-specific tool wrappers
- MailMind entrypoints and documentation

`src/mailmind/` still exists as a compatibility layer during the refactor so existing behavior does not break abruptly. New concrete-agent work should go under `agents/mailmind/`.

## Target Structure

```text
project_root/
  agents/
    mailmind/
      agent.py
      cli.py
      config.py
      planner.py
      prompts/
      tools/
      policies/
      README.md
    coding_agent/
    brainstorming_agent/
    orchestrator/
  pyproject.toml
  README.md
  src/agents/
  src/interfaces/
  src/llm/
  src/memory/
  src/planner/
  src/platform_logging/
  src/schemas/
  src/storage/
  src/tools/
  src/utils/
  tests/
```

## Platform Vs Agent

Shared platform code:

- [`src/llm`](src/llm): generic LLM interfaces and factories
- [`src/tools`](src/tools): generic tool framework
- [`src/planner`](src/planner): generic planner interfaces and router
- [`src/memory`](src/memory): generic session and conversation memory
- [`src/memory`](src/memory): layered long-term memory, retrieval, policies, and session memory
- [`src/storage`](src/storage): generic storage abstractions
- [`src/platform_logging`](src/platform_logging): shared logging adapters
- [`src/schemas`](src/schemas): common schemas
- [`src/agents`](src/agents): reusable base agent and ReAct agent
- [`src/interfaces`](src/interfaces): reusable channel adapters
- [`src/utils`](src/utils): shared config/time/id helpers

MailMind concrete agent:

- [`agents/mailmind`](agents/mailmind): MailMind-specific agent package
- [`agents/mailmind/policies`](agents/mailmind/policies): MailMind policy files
- [`agents/mailmind/tools`](agents/mailmind/tools): MailMind-specific tool wrappers

Existing compatibility/runtime modules still used during migration:

- [`src/mailmind`](src/mailmind): compatibility layer and existing runtime wiring
- [`src/tools`](src/tools): the base tool interface, tool registry, executor, and currently-shared concrete tools for fetch/search/classify/draft/notify/summary.

## Shared Examples

Shared global LLM usage:

```python
from llm.factory import LLMFactory

default_llm = LLMFactory.build_default_local_llm()
```

MailMind-specific LLM override:

```python
from agents.mailmind.agent import MailMindAgentApp

mailmind_app = MailMindAgentApp.from_env()
mailmind_llm = MailMindAgentApp.default_llm_example()
```

MailMind tool inheriting from shared `BaseTool`:

```python
from agents.mailmind.tools.email_search import MailMindEmailSearchTool
from tools.base import BaseTool

assert issubclass(MailMindEmailSearchTool, BaseTool)
```

## Adding Agents

To add a new concrete agent:

1. Create a new package under [`agents/`](agents), for example `agents/coding_agent/`.
2. Put only domain-specific prompts, policies, config, and tool wrappers there.
3. Reuse shared abstractions from [`src/llm`](src/llm), [`src/tools`](src/tools), [`src/planner`](src/planner), [`src/memory`](src/memory), [`src/storage`](src/storage), and [`src/agents`](src/agents).
4. If a new helper is reusable beyond one agent, move it into `src/` instead of keeping it in the agent package.
5. Keep dependency direction one-way: `agents/*` may import from `src/*`, but `src/*` must not import from `agents/*`.

## MailMind

MailMind remains responsible for:

- fetching emails
- classifying emails
- searching and summarizing emails
- drafting replies
- handling WhatsApp notifications

It consumes the shared platform rather than defining the platform.

## Tool Catalog

The platform maintains a JSON tool catalog generated from registered tools and their Pydantic input schemas. By default it is written to [`data/tool_catalog.json`](data/tool_catalog.json) and can be passed to Function Gemma for tool selection.

## ReAct Graph

The conversational agent now runs as a LangGraph state machine:

```text
User / WhatsApp / CLI
        |
        v
  ConversationMemory.load(session_id)
        |
        v
      START
        |
        v
    [reason]
      planner.plan(user_input, memory, observation)
        |
        +--> respond_directly / done ----> [respond] ----> END
        |
        +--> tool_call ------------------> [act]
                                           |
                                           v
                                 ToolExecutor.execute(...)
                                           |
                                           v
                                       observation
                                           |
                                           v
                                        [reason]
```

This is used for multi-turn flows such as:

1. `what emails today?`
2. `email_search`
3. `email_summary`
4. agent asks for clarification
5. `job ones`
6. `email_search(category=strong_ml_research_job)`
7. agent responds with the narrowed result

## Tool System

The current foundation is tool-driven rather than script-driven:

- Every tool subclasses [`BaseTool`](src/tools/base.py) and declares strict Pydantic input/output schemas.
- [`ToolRegistry`](src/tools/registry.py) holds reusable tools by name.
- [`ToolExecutor`](src/tools/executor.py) validates inputs, executes tools, validates outputs, and logs each execution into SQLite.
- [`RuleBasedToolPlanner`](src/mailmind/agents/planner.py) does simple rule-based tool selection first.
- [`FunctionCallingToolPlanner`](src/mailmind/agents/function_planner.py) uses Function Gemma for tool selection, with the rule planner as fallback.
- [`OptionalLLMToolPlanner`](src/mailmind/agents/llm_planner.py) is the plug-in point for LLM-based planning and falls back to rules on errors.
- [`ReActAgent`](src/mailmind/agent/react_agent.py) runs the conversational loop on top of LangGraph.

The implemented v1 tools are:

- `gmail_fetch`
- `email_search`
- `email_classifier`
- `draft_reply`
- `notification`
- `email_summary`

`email_search` is the primary query tool and supports keyword, sender, category, and time-based filtering directly against SQLite.
The current search/planner path supports queries like `emails today`, `job emails today`, `events this week`, and `emails from deepmind`.
`email_summary` now returns structured totals and category counts for follow-up prompts.

## Memory System

The shared memory system is JSON-first and database-backed:

- [`src/memory/models.py`](src/memory/models.py): strict `MemoryItem` and `SleepingTask` schemas
- [`src/memory/layers.py`](src/memory/layers.py): hot in-memory cache, warm SQLite + FTS storage, cold JSON archive
- [`src/memory/store.py`](src/memory/store.py): write routing, promotion, and archival
- [`src/memory/retriever.py`](src/memory/retriever.py): layered retrieval and ranking
- [`src/memory/policies.py`](src/memory/policies.py): write policy for tool execution, classification, reflection, and errors
- [`src/memory/sleeping.py`](src/memory/sleeping.py): deferred background task queue

Memory types are:

- `semantic`
- `episodic`
- `error`
- `reflection`
- `task`

Storage layers are:

- `hot`: recent in-memory cache
- `warm`: primary SQLite store with FTS
- `cold`: archived JSONL storage

MailMind now wires this shared memory system into:

- the shared ReAct agent, which retrieves memory context before planning
- the tool executor, which records tool execution and tool failures
- the MailMind orchestrator, which records classification memories

Example:

```python
from pathlib import Path

from memory import ColdMemoryLayer, HotMemoryLayer, MemoryIndexer, MemoryItem, MemoryRetriever, MemoryStore, WarmMemoryLayer

warm = WarmMemoryLayer(Path("data/mailmind.db"))
store = MemoryStore(
    hot_layer=HotMemoryLayer(),
    warm_layer=warm,
    cold_layer=ColdMemoryLayer(Path("data/memory/cold_memories.jsonl")),
    indexer=MemoryIndexer(warm_layer=warm),
)
retriever = MemoryRetriever(store=store)

store.add(
    MemoryItem(
        type="semantic",
        layer="warm",
        content={"fact": "User prefers research-heavy roles"},
        metadata={"agent": "mailmind"},
    )
)

memories = retriever.retrieve("research-heavy roles", filters={"type": "semantic"})
```

## Design Notes

- SQLite is the canonical store to keep the first version robust, inspectable, and easy to extend.
- SQLite now also stores `tool_logs`, so agent/tool execution is queryable locally.
- Structured audit logs are written separately to JSONL so side effects and domain events remain easy to inspect outside the database.
- Policies are YAML-driven through [`policies/default_policy.yaml`](policies/default_policy.yaml), which keeps prioritization easy to tune without editing code.
- External integrations are stubbed safely. Search for `TODO` markers before wiring real Gmail OAuth or WhatsApp provider credentials.
- For WhatsApp, the config surface now matches Twilio credential names so deployment wiring is less ambiguous.
- Email content is treated as untrusted input. v0.1 keeps parsing simple and local; richer MIME handling belongs in the real Gmail adapter.

## Setup

```bash
source ./setup.sh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

If you want the top-level `src` directory on `PYTHONPATH` for shell sessions and ad hoc scripts, run:

```bash
source ./setup.sh
```

## Configuration

Runtime settings now load from [`config/mailmind.yaml`](config/mailmind.yaml) by default. This is the main place to configure:

- SQLite path and JSONL log path
- policy file path
- source mode and seed inbox path
- classifier mode and optional LLM toggle
- local LLM provider, model, and inference settings
- planner LLM provider/model settings for tool selection
- memory hot-cache size, archival threshold, and cold-storage paths
- WhatsApp mode, destination, and allowlist
- Twilio WhatsApp credentials and sender id
- viewer host and port

Environment variables still override file values when needed. The config path itself can be changed with `MAILMIND_CONFIG_PATH`.
The application now auto-loads a local `.env` file on startup, so Gmail and Twilio credentials do not need to be exported manually in the shell.
For local inference, install the optional extra with `pip install -e ".[local-llm]"`.
Function Gemma tool selection is configured independently from the classifier model. The planner defaults to `google/functiongemma-270m-it`.

For machine-specific secrets or private destinations, start from [`config/mailmind.local.yaml.example`](config/mailmind.local.yaml.example) and point `MAILMIND_CONFIG_PATH` at your local copy, or keep secrets in environment variables.

## CLI

Initialize the database:

```bash
mailmind init-db
```

Seed demo data and process it through the full loop:

```bash
mailmind seed-demo-data
```

Fetch and process emails through the tool system:

```bash
mailmind fetch-emails
```

Query stored emails directly through the search tool:

```bash
mailmind list-emails --category strong_ml_research_job --sender deepmind
```

Run the agent planner + executor:

```bash
mailmind run-agent "show me job emails today"
```

Run a local multi-turn chat simulation:

```bash
mailmind run-chat --session-id demo
```

Run the mock WhatsApp entrypoint:

```bash
mailmind run-whatsapp-mock "what emails today?" --session-id wa-demo
```

Inspect registered tools from the local viewer API:

```bash
curl "http://127.0.0.1:8000/api/tools"
```

Run a single polling cycle against the configured source:

```bash
mailmind run-poller --once
```

Start the local viewer on `localhost`:

```bash
mailmind run-viewer
```

The current default notification destination is defined in [`config/mailmind.yaml`](config/mailmind.yaml).

Approve or reject an outbound WhatsApp notification:

```bash
mailmind approve <approval-id>
mailmind reject <approval-id> --reason "Not needed"
```

Reprocess a message already in storage:

```bash
mailmind reprocess-email <message-id>
```

## Demo Workflow

1. Run `mailmind init-db`.
2. Run `mailmind seed-demo-data`.
3. Open the viewer and inspect `/`, `/important`, `/approvals`, `/drafts`, `/logs`, and `/settings`.
   The viewer also exposes `/emails` and `/search`.
4. Approve a queued notification from the CLI when you want the fake WhatsApp adapter to record a send attempt.

## Testing

```bash
pytest
```

The test suite covers policy loading, rules classification, repository round-trips, tool registry/execution, Function Gemma catalog/parsing, planner behavior, ReAct multi-turn behavior, WhatsApp mock behavior, orchestrator behavior, and an integration-style fake-adapter pipeline.

## Real Integration Gaps

- Gmail: OAuth setup, token persistence, incremental sync state, MIME parsing, and Gmail label/archive actions are still TODOs in [`sources/gmail.py`](src/mailmind/sources/gmail.py).
- WhatsApp: provider credentials, signed API calls, rate limiting, retry semantics, and delivery receipt handling are still TODOs in [`notifiers/whatsapp.py`](src/mailmind/notifiers/whatsapp.py).
- Twilio-specific env/config names are `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `MAILMIND_TWILIO_WHATSAPP_FROM`.
- LLM classification can now run locally through [`HuggingFaceLLM`](src/LLM/huggingface.py). [`Qwen3_1_7BLLM`](src/LLM/qwen.py) inherits from it for `Qwen/Qwen3-1.7B`. If local inference is unavailable or returns invalid JSON, the adapter falls back to rules.
- Tool selection can use [`FunctionGemmaLLM`](src/LLM/function_gemma.py), which consumes the generated JSON tool catalog and returns a function-style tool call. If unavailable, planning falls back to rules.
