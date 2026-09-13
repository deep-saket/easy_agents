# Getting Started

This guide gets the current repository running without an API key or network-backed service. It uses the deterministic path in `SimpleConversationAgent`, in-memory working memory, and the mock WhatsApp adapter.

For a description of everything that is implemented today, see [Current Capabilities](./reference/current-capabilities.md). To build a new agent, continue with [Create an Agent](./guides/create-an-agent.md).

For per-feature usage and test evidence, use the [Functionality Catalog and Verification Matrix](./reference/functionalities/README.md).

## Prerequisites

- Python 3.11 or newer
- Git
- A POSIX shell for the commands below; on Windows, use the equivalent virtual-environment activation command

Optional integrations have additional dependencies and credentials. You do not need them for this guide.

## Install the Project

Run these commands from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The distribution name in `pyproject.toml` is currently `easy_agent`, while source imports inside the checkout use the `src.*` namespace. Run examples and tests from the repository root until the package namespace is normalized.

Optional dependency groups are available for specific workloads:

```bash
# Hugging Face local-model adapters
python -m pip install -e ".[local-llm]"

# FAISS-backed vector memory
python -m pip install -e ".[memory-vector]"

# Local embedding models for vector memory
python -m pip install -e ".[memory-vector-local]"

# Gmail integration
python -m pip install -e ".[gmail]"

# Pipecat voice runtime
python -m pip install -e ".[voice-realtime]"
```

Installing a local-model dependency does not automatically make the first run offline. Model weights must already be present locally or will need to be downloaded once.

## Run an Offline Smoke Test

With the virtual environment active, run:

```bash
python - <<'PY'
from agents.simple_conversation.agent import SimpleConversationAgent
from src.interfaces.whatsapp import MockWhatsAppInterface
from src.memory import WorkingMemory

memory = WorkingMemory(session_id="getting-started")
channel = MockWhatsAppInterface()
agent = SimpleConversationAgent(
    llm=None,
    memory=memory,
    whatsapp=channel,
)

print(agent.run("My name is Ada", session_id="getting-started"))
print(agent.run("What is my name?", session_id="getting-started"))
PY
```

Expected output:

```text
I'll remember that.
Your name is Ada.
```

This exercises a compiled LangGraph, reusable framework nodes, working memory, and a mock channel. The two recognized name-related turns are deterministic; other prompts need an LLM to produce a useful response.

## Run the Focused Offline Tests

Start with the framework tests that do not require credentials or hosted services:

```bash
python -m pytest -q \
  tests/test_math_tools.py \
  tests/test_agent_node.py \
  tests/test_memory_system.py \
  tests/test_graph_builder_api.py
```

The complete test directory currently mixes unit tests with provider and integration checks. Some tests can depend on local environment variables, credentials, model runtimes, or network access. Read the test before enabling those integrations.

## Open the Graph Builder

The graph builder is a local UI for arranging nodes, checking graph structure, and exporting a JSON spec or Python scaffold:

```bash
./run/graph_builder.sh
```

Open `http://127.0.0.1:8020`. A health check is available at `http://127.0.0.1:8020/health`.

The current Python export is a scaffold, not a fully wired and executable agent. Bind node dependencies, tools, models, storage, and routing in Python before treating an export as runnable.

## Choose an Existing Agent

| Agent | Best use today | How to start |
| --- | --- | --- |
| Simple Conversation | Small offline example of graph, working memory, tracing, and a mock/WhatsApp channel | Use the smoke test above and [its guide](./agents/simple-conversation.md) |
| Collection Agent | Most complete domain workflow; collections, verification, negotiation, helper-agent routing, evaluation, UI, and voice options | Follow the [Collection Agent README](../agents/collection_agent/README.md) |
| MailMind | Email ingestion, classification, search, summarization, drafting, approvals, sending, and WhatsApp notifications | Read the [MailMind overview](./agents/mailmind/overview.md) and its checked-in `config.yml` |
| Discount Planning Agent | Specialist recommendation agent called by Collection Agent | Read its [README](../agents/discount_planning_agent/README.md) |
| Collection Memory Helper | Extracts and stores collection key-event memory | Read its [README](../agents/collection_memory_helper_agent/README.md) |

The brainstorming, coding, and general orchestrator directories are placeholders, not finished agents.

## Configuration Basics

`AppSettings.from_env()` uses this precedence:

1. built-in defaults
2. the YAML file selected by `EASY_AGENT_CONFIG_PATH`
3. process environment variables

A repository-root `.env` file is loaded first, but only fills variables that are not already set in the process. Framework variables generally use the `EASY_AGENT_` prefix. Provider credentials use their provider-specific names, such as `OPENAI_API_KEY`, `GROQ_API_KEY`, or Twilio variables.

Use [`.env.example`](../.env.example) as the starting point. Never commit a populated `.env`, OAuth token, model-provider key, or customer data.

## Next Steps

- [Create an Agent](./guides/create-an-agent.md)
- [Current Capabilities](./reference/current-capabilities.md)
- [Functionality Catalog and Verification Matrix](./reference/functionalities/README.md)
- [Framework Overview](./architecture/framework-overview.md)
- [Memory Architecture](./architecture/memory-architecture.md)
- [Offline Agent Platform Roadmap](./plans/offline-agent-platform-roadmap.md)
