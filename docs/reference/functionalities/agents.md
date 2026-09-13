# Concrete Agents

Status: mixed. Read each section before choosing an agent as a foundation.

## Simple Conversation Agent

Status: smoke verified.

Functionality:

- compiled LangGraph conversation flow
- deterministic name capture and recall
- working-memory update
- response generation
- mock or Twilio WhatsApp delivery
- execution trace support

A two-turn, no-model smoke returned:

```text
I'll remember that.
Your name is Ada.
```

Use the [Simple Conversation guide](../../agents/simple-conversation.md). It is a teaching example, not a general assistant.

## MailMind

Status: locally verified with fake services.

Functionality:

- email ingestion and normalization
- rule or model classification
- stored-email search and summary
- reply drafting
- approval routing
- approved notification and email sending
- working/long-term memory nodes
- mock or Twilio WhatsApp response

Sixteen focused tests passed across the MailMind graph, routers, classifier, source normalization, summary, drafts, notification approval, and fake-backed sending.

Inspect CLI options without loading a model:

```bash
python agents/mailmind/main.py --help
```

The default builder currently constructs the configured LLM even when `runtime.llm_enabled` is false. A normal CLI run may therefore require the `local-llm` extra and local/cached model weights. Live Gmail and Twilio were not tested.

See [MailMind Overview](../../agents/mailmind/overview.md).

## Collection Agent

Status: partially verified; not regression-clean.

Functionality includes:

- customer/case/policy context loading
- right-party and identity verification
- collections intent/entity extraction
- full and partial payment paths
- payment links and confirmations
- promise-to-pay capture and follow-up
- hardship, premium hold, discount, and human-escalation paths
- outbound callback scheduling/cancellation
- plan tree/state/directive generation
- specialist-agent routing
- traces, evaluation data, UI, and optional voice runtime

The focused domain suite result was:

```text
117 passed, 22 failed
```

Failures by test module:

| Module | Failed |
| --- | ---: |
| `test_collection_plan_proposal_node.py` | 1 |
| `test_collection_response_node.py` | 2 |
| `test_installment_discount_flow.py` | 5 |
| `test_outbound_callback_scheduler.py` | 3 |
| `test_plan_proposal_split_nodes.py` | 5 |
| `test_promise_to_pay_flow.py` | 3 |
| `test_required_entity_fallback.py` | 3 |

Passing paths include context building, reflection safety, full payment, most discount/partial-payment flows, negotiation classification, most callback operations, plan synchronization, premium holds, and most promise-to-pay behavior. The failures show that several state-transition and wording contracts have drifted; do not treat those paths as release-ready until reconciled.

Inspect CLI options with:

```bash
python -m agents.collection_agent.main --help
```

For model, UI, voice, data, graph, and run instructions, see the [Collection Agent README](../../../agents/collection_agent/README.md).

## Conversation Manager

Status: verified against its local regression suite.

This collection-specific wrapper owns wait fillers, latest-input-wins behavior, stale-response suppression, replay, interruption handoff, delivery tracking, and voice barge-in state. It is not a LangGraph graph and not a general orchestrator.

Seventeen focused tests passed, including response timing, repeat detection, supersession, reset, voice interruption, closing grace periods, runtime wrapping, and missing-Pipecat failure behavior.

See the [Conversation Manager README](../../../agents/collection_agent/conversation_manager/README.md).

## Discount Planning Agent

Status: smoke verified.

This synchronous specialist accepts a structured dictionary and returns a recommended restructure, two variants, rationale, compliance flags, confidence, and next-action hint. A deterministic smoke verified target-EMI propagation and variant generation.

Run its sample from the repository root:

```bash
python -m agents.discount_planning_agent.main
```

Its `compliance_flags` explicitly say the demo policy check is pending; it is not a production underwriting or settlement engine.

## Collection Memory Helper

Status: smoke verified with temporary storage.

This graph-based helper extracts collection key events, updates global and user JSON memories, reflects on completion, and returns a diagnostic response. A no-model smoke verified both JSON files and the `updated` tool result in an isolated temporary directory.

Its checked-in sample writes under Collection Agent runtime storage:

```bash
python -m agents.collection_memory_helper_agent.main
```

Use only test data unless retention and privacy rules are defined.

## Placeholder Agents

The brainstorming, coding, and general orchestrator packages contain only placeholder `__init__.py` files. They have no runtime, graph, CLI, or tests and were not assigned a functional status.

Use [Create an Agent](../../guides/create-an-agent.md) to implement one and the [platform roadmap](../../plans/offline-agent-platform-roadmap.md) for the intended agent-army architecture.
