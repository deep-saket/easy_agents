# mailmind

`mailmind` is a local-first email triage engine for a machine learning researcher/engineer. It fetches messages, classifies them against explicit user policy, generates drafts for relevant items, gates outbound notifications behind approval, stores canonical state in SQLite, writes structured JSONL audit logs, and exposes a local FastAPI viewer.

Before writing code, the file tree created for this project was:

```text
mailmind/
  pyproject.toml
  README.md
  .env.example
  config/
    mailmind.yaml
    mailmind.local.yaml.example
  policies/
    default_policy.yaml
  data/
    logs/
    seed/
  src/mailmind/
    agents/
    core/
    schemas/
    sources/
    classifiers/
    drafters/
    notifiers/
    approvals/
    storage/
    logs/
    viewer/
    cli/
  src/LLM/
  src/tools/
  tests/
```

## Architecture

The code is split by responsibility under [`src/mailmind`](/Users/saketm10/Projects/openclaw_agents/src/mailmind):

- [`agent`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/agent): the LangGraph-backed `ReActAgent`.
- [`agents`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/agents): an `Agent` plus a rule-based `ToolPlanner` that converts user queries into structured tool calls.
- [`core`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/core): domain models, interfaces, policy loading, and the event-driven orchestrator.
- [`memory`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/memory): conversation history and session state persisted in SQLite.
- [`interface`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/interface): channel adapters, including a mock WhatsApp interface.
- [`src/LLM`](/Users/saketm10/Projects/openclaw_agents/src/LLM): shared local Hugging Face LLM clients, including a reusable `HuggingFaceLLM` and a `Qwen/Qwen3-1.7B` subclass.
- [`schemas`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/schemas): shared Pydantic schemas used across tools and agents.
- [`src/tools`](/Users/saketm10/Projects/openclaw_agents/src/tools): the base tool interface, tool registry, executor, and concrete tools for fetch/search/classify/draft/notify/summary.
- [`sources`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/sources): Gmail adapters. v0.1 defaults to a fake Gmail source seeded from local JSON.
- [`classifiers`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/classifiers): rules-based classifier plus an optional local-LLM classifier adapter.
- [`drafters`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/drafters): reply draft generation.
- [`notifiers`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/notifiers): WhatsApp adapters. v0.1 ships with a safe fake notifier and a real-integration stub.
- [`approvals`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/approvals): local approval queue backed by SQLite.
- [`storage`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/storage): SQLite repository for messages, classifications, drafts, approvals, notifications, and processing state.
- [`logs`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/logs): structured JSONL audit logging under `data/logs/`.
- [`viewer`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/viewer): local-only FastAPI/Jinja viewer.
- [`cli`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/cli): development and operator commands.

The container in [`container.py`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/container.py) wires the interfaces together with simple dependency injection, so future sources, notifiers, or agent channels can be swapped in without changing the orchestrator.

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

- Every tool subclasses [`BaseTool`](/Users/saketm10/Projects/openclaw_agents/src/tools/base.py) and declares strict Pydantic input/output schemas.
- [`ToolRegistry`](/Users/saketm10/Projects/openclaw_agents/src/tools/registry.py) holds reusable tools by name.
- [`ToolExecutor`](/Users/saketm10/Projects/openclaw_agents/src/tools/executor.py) validates inputs, executes tools, validates outputs, and logs each execution into SQLite.
- [`RuleBasedToolPlanner`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/agents/planner.py) does simple rule-based tool selection first.
- [`OptionalLLMToolPlanner`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/agents/llm_planner.py) is the plug-in point for LLM-based planning and falls back to rules on errors.
- [`ReActAgent`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/agent/react_agent.py) runs the conversational loop on top of LangGraph.

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

## Design Notes

- SQLite is the canonical store to keep the first version robust, inspectable, and easy to extend.
- SQLite now also stores `tool_logs`, so agent/tool execution is queryable locally.
- Structured audit logs are written separately to JSONL so side effects and domain events remain easy to inspect outside the database.
- Policies are YAML-driven through [`policies/default_policy.yaml`](/Users/saketm10/Projects/openclaw_agents/policies/default_policy.yaml), which keeps prioritization easy to tune without editing code.
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

Runtime settings now load from [`config/mailmind.yaml`](/Users/saketm10/Projects/openclaw_agents/config/mailmind.yaml) by default. This is the main place to configure:

- SQLite path and JSONL log path
- policy file path
- source mode and seed inbox path
- classifier mode and optional LLM toggle
- local LLM provider, model, and inference settings
- WhatsApp mode, destination, and allowlist
- Twilio WhatsApp credentials and sender id
- viewer host and port

Environment variables still override file values when needed. The config path itself can be changed with `MAILMIND_CONFIG_PATH`.
The application now auto-loads a local `.env` file on startup, so Gmail and Twilio credentials do not need to be exported manually in the shell.
For local inference, install the optional extra with `pip install -e ".[local-llm]"`.

For machine-specific secrets or private destinations, start from [`config/mailmind.local.yaml.example`](/Users/saketm10/Projects/openclaw_agents/config/mailmind.local.yaml.example) and point `MAILMIND_CONFIG_PATH` at your local copy, or keep secrets in environment variables.

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

The current default notification destination is defined in [`config/mailmind.yaml`](/Users/saketm10/Projects/openclaw_agents/config/mailmind.yaml).

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

The test suite covers policy loading, rules classification, repository round-trips, tool registry/execution, planner behavior, ReAct multi-turn behavior, WhatsApp mock behavior, orchestrator behavior, and an integration-style fake-adapter pipeline.

## Real Integration Gaps

- Gmail: OAuth setup, token persistence, incremental sync state, MIME parsing, and Gmail label/archive actions are still TODOs in [`sources/gmail.py`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/sources/gmail.py).
- WhatsApp: provider credentials, signed API calls, rate limiting, retry semantics, and delivery receipt handling are still TODOs in [`notifiers/whatsapp.py`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/notifiers/whatsapp.py).
- Twilio-specific env/config names are `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `MAILMIND_TWILIO_WHATSAPP_FROM`.
- LLM classification can now run locally through [`HuggingFaceLLM`](/Users/saketm10/Projects/openclaw_agents/src/LLM/huggingface.py). [`Qwen3_1_7BLLM`](/Users/saketm10/Projects/openclaw_agents/src/LLM/qwen.py) inherits from it for `Qwen/Qwen3-1.7B`. If local inference is unavailable or returns invalid JSON, the adapter falls back to rules.
