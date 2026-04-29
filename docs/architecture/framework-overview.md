# Framework Overview

`easy_agents` is a framework-first repository for building local multi-agent systems.

The Python package/distribution name remains `easy_agent`.

The shared framework lives under `src/`. Concrete agents, examples, or experiments may live outside it, but `src/` is intended to be usable as a standalone foundation.

## Current State

- The old `src/mailmind` package has been removed.
- Shared runtime dependencies previously living there have been extracted into `src/`.
- The package metadata now uses the framework name `easy_agent`.
- Concrete agents live under `agents/`.
- The MailMind runtime now lives under `agents/mailmind/`.

## Repository Structure

```text
project_root/
  agents/
    simple_conversation/
    brainstorming_agent/
    coding_agent/
    mailmind/
    orchestrator/
  docs/
  endpoints/
  src/
  tests/
  pyproject.toml
  README.md
```

## What Lives In `src/`

- `src/agents`: shared agent runtimes and reusable graph nodes
- `src/interfaces`: channel and repository protocols
- `src/llm`: model adapters and function-calling helpers
- `src/memory`: conversation memory plus layered long-term memory
- `src/platform_logging`: tracing and audit logging
- `src/schemas`: shared domain models and tool I/O schemas
- `src/storage`: JSONL and DuckDB-backed storage implementations
- `src/tools`: tool base classes, registry, executor, and concrete tools
- `src/utils`: shared config, time, and id helpers

## Runtime Model

The shared runtime centers on `src/agents/graph_agent.py`.

At a high level, a turn flows like this:

1. load session memory
2. retrieve working and long-term memory context
3. plan the next step
4. optionally execute a tool
5. reflect or write memory
6. produce the final response

This is implemented with reusable nodes under `src/nodes/`.

`AgentNode` allows nesting one full agent runtime as a node inside another
graph, enabling agent-of-agents composition without rewriting capability logic.

## Example Agents

- [Simple Conversation Agent](../agents/simple-conversation.md)
- [MailMind](../agents/mailmind/overview.md)
- [Brainstorming Agent](../agents/brainstorming-agent.md)
- [Coding Agent](../agents/coding-agent.md)
- [Orchestrator Agent](../agents/orchestrator-agent.md)

## Tools

The framework exposes a reusable tool system:

- `BaseTool`
- `ToolRegistry`
- `ToolExecutor`

Concrete tools currently include:

- generic framework examples, such as `src/tools/math`
- email-oriented tools under `src/tools/gmail`
- memory tools under `src/tools`

## Configuration

Shared settings are defined in `src/utils/config.py`.

Current behavior:

- a YAML config file can provide defaults
- a local `.env` file is auto-loaded if present
- environment variables use the `EASY_AGENT_` prefix for framework settings

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
