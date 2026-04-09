# easy_agents

`easy_agents` is a framework-first repository for building local multi-agent systems.

The Python package/distribution name remains `easy_agent`.

The shared framework lives under [`src/`](src). Concrete agents, examples, or experiments may live outside it, but `src/` is intended to be usable as a standalone foundation.

## Current State

- The old `src/mailmind` package has been removed.
- Shared runtime dependencies previously living there have been extracted into `src/`.
- The package metadata now uses the framework name `easy_agent`.
- There is currently no CLI entrypoint.
- The only concrete agent that is currently wired to the shared framework is the simple conversation example in [`agents/simple_conversation/`](agents/simple_conversation).
- Some tests and docs still reference old MailMind-era modules and will be migrated later.

## Repository Structure

```text
project_root/
  agents/
    simple_conversation/
    brainstorming_agent/
    coding_agent/
    orchestrator/
  endpoints/
  src/
    agents/
    interfaces/
    llm/
    memory/
    planner/
    platform_logging/
    schemas/
    storage/
    tools/
    utils/
  tests/
  pyproject.toml
  README.md
```

## What Lives In `src/`

- [`src/agents`](src/agents): shared agent runtimes and reusable graph nodes
- [`src/interfaces`](src/interfaces): channel and repository protocols
- [`src/llm`](src/llm): model adapters and function-calling helpers
- [`src/memory`](src/memory): conversation memory plus layered long-term memory
- [`src/planner`](src/planner): planner abstractions
- [`src/platform_logging`](src/platform_logging): tracing and audit logging
- [`src/schemas`](src/schemas): shared domain models and tool I/O schemas
- [`src/storage`](src/storage): JSONL and DuckDB-backed storage implementations
- [`src/tools`](src/tools): tool base classes, registry, executor, and concrete tools
- [`src/utils`](src/utils): shared config, time, and id helpers

## Runtime Model

The shared runtime centers on the graph agent in [src/agents/graph_agent.py](/Users/saketm10/Projects/easy_agents/src/agents/graph_agent.py).

At a high level, a turn flows like this:

1. load session memory
2. retrieve working and long-term memory context
3. plan the next step
4. optionally execute a tool
5. reflect or write memory
6. produce the final response

This is implemented with reusable nodes under [`src/agents/nodes`](src/agents/nodes).

## Shared Components Added During Migration

The framework now contains the shared pieces that previously only existed under the deleted MailMind package:

- domain records in [src/schemas/domain.py](/Users/saketm10/Projects/easy_agents/src/schemas/domain.py)
- email view schemas in [src/schemas/emails.py](/Users/saketm10/Projects/easy_agents/src/schemas/emails.py)
- tool I/O schemas in [src/schemas/tool_io.py](/Users/saketm10/Projects/easy_agents/src/schemas/tool_io.py)
- repository and email protocols in [src/interfaces/email.py](/Users/saketm10/Projects/easy_agents/src/interfaces/email.py)
- shared config in [src/utils/config.py](/Users/saketm10/Projects/easy_agents/src/utils/config.py)
- JSONL audit storage in [src/storage/json_store.py](/Users/saketm10/Projects/easy_agents/src/storage/json_store.py)
- DuckDB repository in [src/storage/duckdb_store.py](/Users/saketm10/Projects/easy_agents/src/storage/duckdb_store.py)

## Available Example Agent

The simple conversation agent in [agents/simple_conversation/agent.py](/Users/saketm10/Projects/easy_agents/agents/simple_conversation/agent.py) is the current example concrete agent.

It demonstrates:

- graph-based turn execution
- working-memory updates
- WhatsApp interface integration
- local trace logging

The FastAPI webhook entrypoint is [endpoints/whatsapp.py](/Users/saketm10/Projects/easy_agents/endpoints/whatsapp.py).

## Tools

The framework exposes a reusable tool system:

- [`BaseTool`](src/tools/base.py)
- [`ToolRegistry`](src/tools/registry.py)
- [`ToolExecutor`](src/tools/executor.py)

There are currently two categories of concrete tools:

- generic framework examples, such as [`src/tools/math`](src/tools/math)
- email-oriented tools under [`src/tools/gmail`](src/tools/gmail)

The email-oriented tools remain in `src/` for now because the framework extraction is still in progress. Their final boundary will be decided later.

## Configuration

Shared settings are defined in [src/utils/config.py](/Users/saketm10/Projects/easy_agents/src/utils/config.py).

Current behavior:

- config defaults load from `config/easy_agent.yaml` if present
- a local `.env` file is auto-loaded if present
- environment variables use the `EASY_AGENT_` prefix for framework settings

Some integration fields are still email or Twilio oriented because current example/runtime code still uses them.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

If you need local model support:

```bash
pip install -e ".[local-llm]"
```

## Testing

```bash
pytest
```

Note: the test suite is still being migrated. Some tests still reference deleted `src.mailmind` modules and are not yet aligned with the current framework layout.

## Status Summary

- `src/` now stands on its own without `src.mailmind`
- core framework imports are working again
- package metadata has been renamed to `easy_agent`
- the source tree is ahead of the tests and documentation cleanup

The tracked migration plan is in [REFACTOR_FIX_PLAN.md](/Users/saketm10/Projects/easy_agents/REFACTOR_FIX_PLAN.md).
