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
    core/
    sources/
    classifiers/
    drafters/
    notifiers/
    approvals/
    storage/
    logs/
    viewer/
    cli/
  tests/
```

## Architecture

The code is split by responsibility under [`src/mailmind`](/Users/saketm10/Projects/openclaw_agents/src/mailmind):

- [`core`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/core): domain models, interfaces, policy loading, and the event-driven orchestrator.
- [`sources`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/sources): Gmail adapters. v0.1 defaults to a fake Gmail source seeded from local JSON.
- [`classifiers`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/classifiers): rules-based classifier plus an optional LLM adapter stub.
- [`drafters`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/drafters): reply draft generation.
- [`notifiers`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/notifiers): WhatsApp adapters. v0.1 ships with a safe fake notifier and a real-integration stub.
- [`approvals`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/approvals): local approval queue backed by SQLite.
- [`storage`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/storage): SQLite repository for messages, classifications, drafts, approvals, notifications, and processing state.
- [`logs`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/logs): structured JSONL audit logging under `data/logs/`.
- [`viewer`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/viewer): local-only FastAPI/Jinja viewer.
- [`cli`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/cli): development and operator commands.

The container in [`container.py`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/container.py) wires the interfaces together with simple dependency injection, so future sources, notifiers, or agent channels can be swapped in without changing the orchestrator.

## Design Notes

- SQLite is the canonical store to keep the first version robust, inspectable, and easy to extend.
- Structured audit logs are written separately to JSONL so side effects and domain events remain easy to inspect outside the database.
- Policies are YAML-driven through [`policies/default_policy.yaml`](/Users/saketm10/Projects/openclaw_agents/policies/default_policy.yaml), which keeps prioritization easy to tune without editing code.
- External integrations are stubbed safely. Search for `TODO` markers before wiring real Gmail OAuth or WhatsApp provider credentials.
- For WhatsApp, the config surface now matches Twilio credential names so deployment wiring is less ambiguous.
- Email content is treated as untrusted input. v0.1 keeps parsing simple and local; richer MIME handling belongs in the real Gmail adapter.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Configuration

Runtime settings now load from [`config/mailmind.yaml`](/Users/saketm10/Projects/openclaw_agents/config/mailmind.yaml) by default. This is the main place to configure:

- SQLite path and JSONL log path
- policy file path
- source mode and seed inbox path
- classifier mode and optional LLM toggle
- WhatsApp mode, destination, and allowlist
- Twilio WhatsApp credentials and sender id
- viewer host and port

Environment variables still override file values when needed. The config path itself can be changed with `MAILMIND_CONFIG_PATH`.

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
4. Approve a queued notification from the CLI when you want the fake WhatsApp adapter to record a send attempt.

## Testing

```bash
pytest
```

The test suite covers policy loading, rules classification, repository round-trips, orchestrator behavior, and an integration-style fake-adapter pipeline.

## Real Integration Gaps

- Gmail: OAuth setup, token persistence, incremental sync state, MIME parsing, and Gmail label/archive actions are still TODOs in [`sources/gmail.py`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/sources/gmail.py).
- WhatsApp: provider credentials, signed API calls, rate limiting, retry semantics, and delivery receipt handling are still TODOs in [`notifiers/whatsapp.py`](/Users/saketm10/Projects/openclaw_agents/src/mailmind/notifiers/whatsapp.py).
- Twilio-specific env/config names are `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `MAILMIND_TWILIO_WHATSAPP_FROM`.
- LLM classification: the optional adapter is a stub that currently falls back to rules and annotates the result.
