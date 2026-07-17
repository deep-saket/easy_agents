# Voice AI Collection Agent Engineering Handbook

**Name:** Ansh Adarsh
**Organization:** EXL Digital 
**Role:** AI Engineer Intern  
**Project:** Voice AI Collection Agent 
**Reporting Manager:** Somya Rai 
**Work period covered:** 18 May to 18 July 2026  
**Primary implementation branch reviewed:** `ansh/collection/easy-agent`  

---

## Document Purpose

This handbook explains the engineering work completed on the Voice AI Collection Agent during my internship at EXL. This documentation contains details about the project and need to understand the business problem, LangGraph architecture, workflow state machines, tool orchestration, runtime persistence, debugging approach, implemented collection workflows, known limitations, and future direction.

The handbook focuses on **why** each engineering change was necessary before explaining **how** it was implemented. It does not treat model prompts as the application architecture. The central design principle of the project is:

> Workflow state determines what must happen, tools perform business actions, and the language model communicates verified outcomes naturally.

The implementation and Git history were reviewed for the period beginning 8 June 2026. Major commits include:

| Date | Commit | Main contribution |
|---|---|---|
| 10 Jun 2026 | `a5631c65` | Conversation flow and workflow reliability |
| 12 Jun 2026 | `e20e9382` | Job-loss premium hold, references, confirmations, named closing |
| 12 Jun 2026 | `3bbd6748` | Discount-after-hold workflow and persistence |
| 16 Jun 2026 | `e3210b59` | Partial-payment lifecycle and callback queue recovery |
| 18 Jun 2026 | `68bf31bb`, `ccf335d0` | Runtime-artifact cleanup |
| 28 Jun 2026 | `5301570d` | Hardship routing, human transfer, closing, and plan synchronization |
| 28 Jun 2026 | `da2a43a1` | Full-payment lifecycle |
| 28 Jun 2026 | `daf174b1` | Reusable auto-pay workflow |
| 2 Jul 2026 | `ae6742b3` | Promise-to-pay, follow-ups, response rendering, helper organization |
| 11 Jul 2026 | `106cca84` | Customer-requested callback and hold-email confirmation fix |

---

# 1. Introduction

## 1.1 Project Overview

The Collection Agent is a stateful conversational AI system for outbound collections interactions. It communicates with customers about overdue installments while enforcing identity verification, privacy, policy eligibility, approved payment arrangements, notification requirements, escalation rules, and conversation closing behavior.

Unlike a basic chatbot, the agent cannot generate an unrestricted answer from a prompt. It operates inside a controlled graph where specialized nodes classify the customer message, extract entities, update state, choose objectives, call tools, validate results, reflect on the plan, and render a customer-safe response.

## 1.2 Business Problem

Collections conversations combine customer service, financial policy, operational actions, and compliance. A useful agent must be able to:

- verify the correct customer before disclosing account details;
- explain the overdue account clearly and respectfully;
- understand willingness and ability to pay;
- support full payment, partial payment, promise-to-pay, hardship, and callback outcomes;
- apply only policy-approved assistance;
- generate references through business tools rather than through the model;
- schedule reminders, callbacks, and follow-ups;
- transfer to a human when automated options are exhausted;
- maintain an auditable state and tool history;
- avoid repeating completed offers or making unsupported promises.

Failure in this domain can create financial, privacy, customer-experience, and regulatory risk. A response that sounds natural but contains an unauthorized discount is more serious than a stylistic defect. Therefore, correctness is defined by the combination of workflow state, policy, tools, and communication.

## 1.3 Engineering Objectives

The work documented here pursued the following objectives:

1. Make collection workflows deterministic where business correctness is required.
2. Retain LLM flexibility for natural language understanding and response quality.
3. Reuse shared capabilities instead of implementing isolated scenario scripts.
4. Keep workflow state as the single source of truth.
5. Execute real actions through typed tools.
6. Synchronize the plan tree with runtime execution.
7. Persist enough evidence to debug every turn.
8. Improve privacy, closing behavior, interruption handling, and specialist transfer.
9. Build regression tests around state, tools, policies, and responses.
10. Prepare the prototype architecture for eventual production services.

## 1.4 Technology Stack

| Area | Technology or pattern | Role |
|---|---|---|
| Language | Python | Agent, graph, tools, services, tests |
| Orchestration | LangGraph | Directed state graph and conditional routing |
| Model layer | Configured LLM provider, including Groq/Ollama-compatible paths during development | Structured classification, extraction fallback, reflection, natural rendering |
| Validation | Pydantic structured models | Typed tool inputs/outputs and structured LLM responses |
| State | `CollectionGraphState` plus conversation memory | Per-turn and cross-turn workflow state |
| Persistence | Local JSON runtime stores | Prototype business records, traces, messages, and queue state |
| Voice/conversation | Pipecat and conversation-manager components | Delivery, interruption, filler, and call termination behavior |
| UI | Local server and Plan Tree Timeline | Runtime inspection and debugging |
| Configuration | YAML and JSON | Prompts, policies, customer/case data, assistance programs, tool catalog |
| Testing | Python test modules with direct workflow/node tests | Regression validation |

## 1.5 Core Design Principle

```text
Customer Input
      |
      v
Hybrid Understanding: deterministic rules first, LLM fallback
      |
      v
Workflow State and Objective Planning
      |
      v
Policy Validation and Tool Execution
      |
      v
Plan Projection and Reflection
      |
      v
Verified Response Context
      |
      v
LLM Rendering with Validation
      |
      +---- invalid/timeout ----> Deterministic Fallback
      |
      v
Customer-Safe Response
```

---

# 2. Collection Agent Architecture

## 2.1 LangGraph Execution Model

The agent is assembled as a `StateGraph(CollectionGraphState)` in `agents/collection_agent/agent.py`. Each graph node receives the current state and returns a partial state update. Conditional edges decide the next node based on route values and verified state.

The active high-level graph is:

```text
START
  |
  v
RelevanceIntentNode
  | relevant
  v
CollectionEntityExtractNode
  |
  v
NegotiationClassificationNode
  |
  v
PrePlanIntentNode
  | plan                         | decide
  v                              v
PlanProposalStateNode     ExecutionPathIntentNode
  |                              |
  v                              +--> MemoryRetrieveNode
PlanProposalGraphNode            +--> VerificationReactNode
  |                              +--> CollectionReactNode
  v                                       |
PlanProposalDirectiveNode                 v
  |                                  ToolExecutionNode
  v                                       |
CollectionReflectNode <-------------------+
  |
  v
CollectionResponseNode
  |
  v
END
```

Irrelevant or empty input uses the irrelevant response path. Verification tools can cycle through `VerificationReactNode` and `ToolExecutionNode`. Business tools cycle through `CollectionReactNode` and `ToolExecutionNode` until the required operation is complete.

## 2.2 Node Responsibilities

| Node | Responsibility | Must not do |
|---|---|---|
| `RelevanceIntentNode` | Decide whether input belongs to the collection conversation | Approve offers or execute tools |
| `CollectionEntityExtractNode` | Extract DOB, mobile, amount, date, and related entities | Choose business outcome |
| `NegotiationClassificationNode` | Classify posture, commitment, offer response, and workflow stage | Persist business actions |
| `PrePlanIntentNode` | Decide whether to plan immediately or continue execution reasoning | Render the final response |
| `ExecutionPathIntentNode` | Decide whether memory, verification, a business tool, or React processing is required | Generate references |
| `MemoryRetrieveNode` | Load relevant memory | Alter policy |
| `VerificationReactNode` | Coordinate identity verification tools | Disclose account data before verification |
| `CollectionReactNode` | Interpret tool observations and select the next business tool | Invent a successful tool result |
| `PlanProposalStateNode` | Prepare normalized planning signals and runtime context | Own the customer wording |
| `PlanProposalGraphNode` | Project workflow progress into the conversation plan | Implement an independent scenario state machine |
| `PlanProposalDirectiveNode` | Select the next objective, dialogue action, and response strategy | Perform external side effects |
| `CollectionReflectNode` | Validate readiness and request correction/replanning | Replace policy validation |
| `CollectionResponseNode` | Communicate verified objectives naturally and safely | Decide workflow, approve discounts, or fabricate actions |
| `ToolExecutionNode` | Execute typed tools and return observations | Infer customer intent |

## 2.3 State Layers

The project uses several related state concepts:

### Graph state

`CollectionGraphState` is the typed LangGraph contract. It contains current input, namespaced intent outputs, observations, plan proposal, conversation plan, verification fields, workflow stages, response metadata, and diagnostics.

### Conversation memory

The memory object carries state across turns. It includes active case/customer context, workflow-specific stages, references, completed objectives, callback status, promise dates, and other values that outlive one graph execution.

### Business records

Tools persist domain actions into runtime JSON files. A payment reference in memory should originate from a persisted payment-link record, not from model text.

### Conversation plan

The plan tree is an observability projection. It displays objectives and statuses such as `pending`, `in_progress`, `done`, `skipped`, or `blocked`. It should reflect graph/runtime evidence and must not become a second business workflow.

## 2.4 Hybrid Understanding

The architecture uses rules and regular expressions for clear cases, followed by LLM fallback for ambiguous natural language. This balance is important:

- deterministic rules are fast, repeatable, and easy to test;
- LLM classification handles indirect or conversational wording;
- workflow state gives meaning to short replies such as “yes,” “not sure,” or “the 30th”;
- the LLM does not directly mutate business state or invoke tools;
- normalized structured output is merged with prior state under deterministic guardrails.

## 2.5 Objective-Driven Planning

Scenarios are useful test descriptions, but they are not the runtime architecture. The system chooses objectives such as:

- verify identity;
- disclose purpose;
- understand hardship;
- present eligible hold;
- assess ability after hold;
- present installment discount;
- collect partial amount;
- create payment link;
- capture promised date;
- schedule callback;
- confirm outcome;
- transfer to specialist;
- close conversation.

Multiple customer journeys can reuse the same objective. For example, a callback can interrupt payment, hardship, verification, or auto-pay without requiring four callback implementations.

## 2.6 Tool Calling

Tools are registered in the agent’s registry and use Pydantic input/output schemas. The standard lifecycle is:

```text
Directive identifies a required business action
  -> ExecutionPathIntentNode selects React/tool path
  -> CollectionReactNode creates tool call
  -> ToolExecutionNode executes registered tool
  -> Tool persists domain record
  -> Typed output becomes observation
  -> React updates workflow state
  -> Planner selects confirmation/next objective
```

`tools/common.py` supports deterministic follow-up decisions, such as scheduling a follow-up after `promise_capture` succeeds.

## 2.7 Configuration-Driven Business Rules

| File | Responsibility |
|---|---|
| `data/policies.json` | Promise windows, partial-payment thresholds, waiver/restructure flags, counter-offer limits |
| `data/assistance_programs.json` | Premium hold and discount eligibility, duration, percentage, approval, channels, review period |
| `data/customers.json` | Customer identity and safe communication variables |
| `data/cases.json` | Case/account context |
| `prompts/agent_prompts.yml` | Structured LLM responsibilities, tone, safety, and response instructions |
| `prompts/tool_catalog.yml` | Tool descriptions available to planning/reasoning |
| `config.yml` | Agent/provider/runtime configuration |

Policy values must be read from configuration or tool output. They should not be hidden in a prompt or duplicated in a response template.

## 2.8 Response Rendering Architecture

The current direction is LLM-first, objective-driven rendering with deterministic fallback:

```text
Current workflow objective
  + verified customer-safe facts
  + latest customer message
  + limited recent context
  + tool-backed outputs
  + compliance constraints
        |
        v
LLM response generation
        |
        v
Response validation
  | valid                         | invalid, timeout, hallucination
  v                               v
Return response             Existing deterministic template
```

Validation checks include unresolved placeholders, invented references, premature claims, privacy leakage, missing callback facts, unsupported offer combinations, and unsupported payment arrangements.

## 2.9 Reflection and Recovery

`CollectionReflectNode` reviews whether the plan/directive is ready for delivery. Reflection can request replanning when structured output, policy alignment, or response readiness fails. It is not a license for the model to alter policy. The reflection loop is bounded by retry counters and correction hints.

## 2.10 Runtime Observability

The local UI exposes:

- execution narrative;
- node timings;
- tool status and results;
- current plan objective;
- Plan Tree Timeline snapshots;
- thinking/reflection trace;
- response target and output.

This UI was central to identifying discrepancies between what the agent said and what the plan/state claimed had happened.

---

# 3. My Internship Journey

## 3.1 Initial Understanding

I began working on the Collection Agent on 2 June 2026. My first task was to understand a repository that combined LangGraph, LLM prompts, tool execution, memory, voice-delivery code, JSON data, runtime persistence, and a debugging UI. The first important lesson was that a conversational response is only the final visible result of a larger stateful system.

I mapped the repository into five concerns:

1. graph orchestration;
2. business workflow state;
3. tools and external side effects;
4. response generation;
5. runtime evidence and observability.

## 3.2 Repository Exploration

I traced the graph from `agent.py`, then followed each node’s state reads and writes. I reviewed `state.py`, tool schemas, policy JSON, assistance programs, customer fixtures, response prompts, runtime files, and tests. I compared the node graph with the Plan Tree Timeline because the two represent different things: the node graph is executable orchestration, while the plan tree is a customer-objective view.

## 3.3 Learning LangGraph

The project taught me how LangGraph uses:

- a typed shared state;
- nodes that return partial updates;
- conditional edges for routing;
- cycles for tools and verification;
- memory across turns;
- explicit terminal response paths;
- state-based debugging instead of only output inspection.

I learned that a correct node sequence does not automatically create a correct business workflow. Domain stages such as `discount_stage` or `promise_stage` must be designed and maintained explicitly.

## 3.4 Learning Workflow Debugging

Many defects initially looked like “the LLM gave the wrong answer.” Detailed inspection often showed a deeper cause:

- the previous objective was still active;
- the correct validation result was not propagated;
- a tool had not executed;
- an acknowledgement was misclassified;
- a stale state value overrode the latest message;
- the response renderer received incomplete verified context;
- the plan tree had implemented its own expected transition.

This changed my debugging approach from prompt-first to state-and-routing-first.

## 3.5 Understanding Business Rules

I learned to separate conversational flexibility from policy authority. A model can express empathy or explain an approved option, but it must not decide the minimum partial amount, discount percentage, hold duration, promise window, or escalation eligibility. Those values belong to configuration, deterministic logic, and tools.

## 3.6 Working with the Debug UI

The Plan Tree Timeline and execution narrative made multi-turn problems visible. For example, the response could say “transfer to a specialist” while the plan showed “confirm agreed outcome.” This was not only a UI issue; it indicated disagreement between the workflow objective and the projection logic.

## 3.7 Runtime State Inspection

I inspected `conversation_states.json`, tool logs, traces, confirmation files, payment records, and callback jobs. Comparing records across turns showed whether an action was actually persisted and whether the next node received the correct evidence.

## 3.8 Session Analysis

Realistic conversations were replayed turn by turn. I recorded:

- source and destination graph nodes;
- state before and after;
- state diff;
- selected objective;
- selected tool and result;
- rendered response;
- plan-tree status;
- latency and reflection retries.

This method supported both bug fixing and Excel-based internal tracking.

## 3.9 Progression of Work

```text
Workflow reliability and opening/privacy
  -> Premium hold lifecycle
  -> Discount-after-hold and confirmations
  -> Partial payment
  -> Closing timer and interruption handling
  -> Human transfer and hardship guardrails
  -> Full payment
  -> Auto-pay
  -> Promise-to-pay and follow-ups
  -> Customer-requested callback
  -> Objective-driven response validation
  -> Runtime plan-tree synchronization
```

---

# 4. Debugging Methodology

## 4.1 Principle: Reproduce Before Changing

For every defect, I first reproduced the conversation and located the exact turn where expected and actual behavior diverged. I avoided treating a different wording as proof of the same root cause. The same repeated sentence can result from classification failure, stale state, tool failure, or response fallback.

## 4.2 Session Replay

Session replay means running the same messages in the same order with the same customer and policy data. It is useful because short responses depend on earlier state. “Yes, please” means different things after a hold offer, an auto-pay offer, or a payment-link question.

Replay checklist:

1. start with a new session ID;
2. record customer/case fixture;
3. submit the exact utterances;
4. save response and execution trace per turn;
5. compare with the expected workflow;
6. repeat after the fix and run adjacent workflows.

## 4.3 Timeline Analysis

The Plan Tree Timeline shows how the customer-facing objectives changed over turns. It is useful for detecting:

- a node that remains pending after execution;
- a completed objective that reopens;
- an unrelated objective marked in progress;
- a privacy branch that incorrectly reaches purpose disclosure;
- closing that remains active after termination;
- transfer missing from the visible plan.

The timeline is evidence, but the underlying workflow state remains authoritative.

## 4.4 State Diff Analysis

State diff analysis compares relevant fields before and after a turn. A typical diff includes:

```text
payment_commitment_type: NONE -> PROMISE_TO_PAY
promise_stage: "" -> date_required
promised_date: "" -> ""
current objective: purpose_disclosure -> promise_to_pay_date_request
```

This explains why a response was generated. It also reveals when a state variable did not change even though the user supplied the required information.

## 4.5 Hop Analysis

A hop records the actual LangGraph source and destination, such as:

```text
NegotiationClassificationNode
  -> PrePlanIntentNode
  -> ExecutionPathIntentNode
  -> CollectionReactNode
  -> ToolExecutionNode
```

Hop analysis distinguishes routing defects from response defects. If the graph never reaches `ToolExecutionNode`, a missing reference is not an SMS-template problem.

## 4.6 Runtime JSON Inspection

Runtime files answer operational questions:

- Was the hold created?
- Was the discount persisted?
- Did a callback job receive a `CALL-...` ID?
- Was a promise follow-up scheduled?
- Did SMS and email confirmation tools run?
- Was the disposition updated?

If the record does not exist, the response must not claim the action occurred.

## 4.7 Tool Log Inspection

`tool_logs.json` and graph observations show tool name, input, output, status, and errors. Tool logs are useful for separating:

- correct routing with tool failure;
- incorrect tool selection;
- malformed arguments;
- successful action with failed state propagation;
- duplicate execution.

## 4.8 Graph Transition Inspection

Conditional edges were inspected in `agent.py` and the route methods. This identifies precedence problems, such as verification routing winning over a callback request, or an execution path returning to planning before the required tool completes.

## 4.9 Reflection Loop Inspection

Long latency can result from repeated structured-output retries or reflection/replanning. The execution narrative exposes `reflect` timings and retry counts. Reflection is useful when it corrects a malformed plan, but a repeated loop may indicate that deterministic workflow state and the LLM schema disagree.

## 4.10 Prompt Versus State Diagnosis

I used the following decision table:

| Symptom | First area to inspect | Why |
|---|---|---|
| Wrong workflow selected | Classification and prior state | Response prompt cannot correct routing safely |
| Correct objective, poor wording | Response context/prompt | Workflow is already correct |
| Correct objective, invented action | Tool evidence and response validation | Prompt alone is insufficient protection |
| Repeated question | Required entity, workflow stage, completion flag | The objective may still be legitimately active |
| Wrong plan-tree status | Runtime state propagation and plan projection | UI should not infer from response text |
| Missing reference | Tool call and persistence | References must not be model-generated |
| Excessive latency | LLM retries, reflection, duplicate planning | Need trace-level timing |

## 4.11 Verification Template for Fixes

Each fix was recorded using:

- Session ID
- Issue Summary
- Customer Query
- Hop: actual graph node to graph node
- Issue Node
- Expected Next Node
- Actual Next Node
- State Before
- State After
- State Diff
- Root Cause Analysis
- Change Made
- Verification Result
- Status

This format forces the diagnosis to identify the executable graph node rather than a visual plan-tree label or unrelated helper function.

---

# 5. Engineering Improvements

This chapter documents the major features and fixes as engineering changes. Each section uses the same structure so that a new developer can compare the problem, design, state, tools, and verification approach consistently.

## 5.1 Opening, Identity Verification, and Privacy Boundaries

### Overview

The opening was updated to identify the agent and company, provide recording disclosure, request the intended customer, and delay account details until verification. Wrong-party responses were separated from right-party verification.

### Problem

Earlier responses could begin with verification details before clearly establishing the right party. A simple “no” was not consistently treated as wrong-party input, and the agent could proceed toward dues disclosure even though verification was skipped.

### Root Cause

- right-party status and verification completion were not consistently represented;
- short negative responses were ambiguous to the LLM;
- the planner could keep the normal collection branch active;
- plan-tree statuses did not enforce the privacy branch.

### Workflow Before

```text
Opening -> Ask DOB/mobile -> possible dues disclosure
                    |
                    +-> "No" could remain ambiguous
```

### Workflow After

```text
Opening and disclosure
  -> Right party?
       -> yes: identity verification -> purpose disclosure
       -> no/wrong party: no account disclosure -> privacy-safe callback
```

### Architecture Changes

- Added/strengthened right-party detection before account disclosure.
- Preserved verified DOB/mobile as separate evidence.
- Added privacy response objectives for wrong-party notice, callback request, and closing.
- Marked account-detail objectives skipped when the privacy branch is active.

### Nodes Changed

| Node | Change |
|---|---|
| `NegotiationClassificationNode` and early intent nodes | Recognize right-party denial in context |
| `VerificationReactNode` | Continue DOB/mobile tools only for the right party |
| `PlanProposalDirectiveNode` | Select privacy-safe objective instead of dues disclosure |
| `PlanProposalGraphNode` | Project verification/purpose as skipped on wrong-party branch |
| `CollectionResponseNode` | Render separate privacy and callback messages |

### State Changes

| Variable | Meaning | Example |
|---|---|---|
| `right_party_status` | Right-party decision | `awaiting_confirmation`, `right_party`, `wrong_party` |
| `verified_dob` | DOB tool result | `true` |
| `verified_mobile` | Mobile tool result | `true` |
| `identity_verified` | Combined verification gate | `true` only when requirements pass |
| `verification_missing_fields` | Fields still required | `['mobile']` |

### Tools

`verify_dob`, `verify_mobile`, `verification_entity_extract`, and `verification_memory_verify` provide typed verification evidence. Verification attempts are persisted independently of response wording.

### Runtime Files

`verification_attempts.json`, `conversation_states.json`, `conversation_messages.json`, and `tool_logs.json`.

### Verification and Testing

Tests cover opening, verification request, privacy notice, dues-before-verification blocking, and plan progression from verification to purpose disclosure.

### Future Improvements

Use a production identity service, field-level PII encryption, attempt limits, fraud monitoring, and auditable consent/recording policies.

### Lessons Learned

Privacy is a state-machine gate. It cannot depend only on a polite prompt.

---

## 5.2 Status Tracking and Plan-Tree Synchronization

### Overview

The Plan Tree Timeline was improved so the displayed objective status follows runtime workflow evidence rather than expected scenario dialogue.

### Problem

Examples included:

- “Initialize case context” remained pending after execution;
- verification was skipped while “Explain dues” appeared in progress;
- hold assessment remained pending after the customer rejected it;
- discount rejection incorrectly activated confirmation;
- human transfer responses had no corresponding plan objective;
- closing remained in progress after the call should end.

### Root Cause

Plan construction and status mutation were distributed across the graph node, directive node, helpers, and response layer. Static topology and inferred dialogue transitions formed a parallel workflow implementation. Stale `current_node_id` and marker values could override current business state.

### Workflow Before

```text
Workflow state ---------> response
Expected scenario logic -> plan tree

Result: response and plan can disagree
```

### Workflow After

```text
Workflow stages + completed objectives + tool observations + disposition
                              |
                              v
                 PlanProposalGraphNode projection
                              |
                              v
                    plan statuses and timeline
```

### Architecture Changes

- Consolidated status reconciliation in `PlanProposalGraphNode`.
- Reduced plan mutation from response delivery.
- Recorded delivered confirmation objectives in `completed_objectives`.
- Used tool-backed evidence for link, promise, callback, discount, and hold completion.
- Enforced one active objective and cleared stale active markers during objective switches.

The current implementation still retains a canonical static topology through base node/edge specifications. Status is dynamic, but a future execution-only tree would materialize only observed objectives and transitions.

### Nodes Changed

| Node | Change |
|---|---|
| `PlanProposalStateNode` | Normalizes state before projection |
| `PlanProposalGraphNode` | Central runtime-state projection and marker reconciliation |
| `PlanProposalDirectiveNode` | Focuses on objective/response strategy rather than visual mutation |
| `CollectionResponseNode` | Records delivered completion evidence without owning graph progression |

### State Changes

| Variable | Purpose |
|---|---|
| `active_conversation_plan` | Current plan projection in memory |
| `conversation_plan.current_node_id` | Active customer objective |
| `step_markers` | `pending`, `in_progress`, `done`, `skipped`, `blocked` |
| `completed_objectives` | Customer-visible objectives already delivered |
| `final_disposition` | Terminal business outcome evidence |
| `observations` | Tool execution evidence |

### Tools

No plan-specific business tool is required for synchronization. The graph consumes observations produced by normal tools. `plan_propose` can persist plan proposals, but it is not the business workflow authority.

### Runtime Files

`conversation_states.json`, `plan_proposals.json`, `tool_logs.json`, and `runtime/traces/`.

### Verification and Testing

`test_plan_graph_verification_sync.py` and `test_plan_graph_objective_sync.py` cover verification, discount rejection, PTP, full payment, auto-pay, escalation, partial payment, and objective switches.

### Future Improvements

Replace the static topology with a dynamic objective execution tree built from runtime objective events. Add explicit event IDs and transition timestamps.

### Lessons Learned

An observability graph should project the workflow. It should never become a second workflow.

---

## 5.3 Conversation Closing, Grace Period, and Interruption Handling

### Overview

Closing behavior was made stateful so completed workflows close politely, wait for a short grace period, accept meaningful revisions, suppress stale responses, and terminate without repeating the previous confirmation.

### Problem

The agent could repeat “You’re welcome. Goodbye” after the call should have ended. It could also terminate before processing a callback-time correction sent immediately after closing. In other cases, a late response from an older request overwrote newer customer input.

### Root Cause

- response text and actual call lifecycle were not synchronized;
- termination did not have explicit closing/grace state;
- every acknowledgement was sent back through the full negotiation workflow;
- concurrent voice/text requests could complete out of order;
- plan completion was marked before or after the wrong event.

### Workflow Before

```text
Agent says goodbye -> next customer message enters normal graph -> old objective may reopen
```

### Workflow After

```text
Workflow confirmation
  -> closing response
  -> conversation_closing=true
  -> grace timer
       -> short acknowledgement: brief goodbye
       -> material revision: cancel/restart closing and process update
       -> timer expires: conversation_complete/terminate_call
       -> late input: reject without new agent response
```

### Architecture Changes

- Added explicit closing and termination metadata.
- Introduced a configurable grace period equivalent to approximately three seconds.
- Preserved “latest input wins” behavior in the conversation manager.
- Distinguished acknowledgements from material changes such as a revised callback time.
- Ensured workflow-specific closing includes the customer name.

### Nodes and Components Changed

| Component | Change |
|---|---|
| `CollectionResponseNode` | Workflow-specific and named closings |
| `PlanProposalDirectiveNode` | Closing objective after confirmed outcomes |
| `PlanProposalGraphNode` | Closing/completed status projection |
| `ConversationManagerAgent` | Stale response suppression, latest-input handling, closure timer |
| `InterruptionPolicy` | Meaningful interruption and replay behavior |
| Pipecat integration | Voice delivery completion and termination metadata |

### State Changes

`conversation_closing`, `conversation_complete`, `terminate_call`, `termination_grace_seconds`, response delivery metadata, and interruption tracking were used to coordinate closing.

### Tools

No business action is replaced by closing. A workflow closes only after required tools and confirmations complete. A revised callback may invoke cancellation/rescheduling tools during the grace window.

### Runtime Files

Conversation-manager logs, `conversation_states.json`, `conversation_messages.json`, and traces.

### Verification and Testing

Tests cover stale response suppression, replay behavior, new business input, voice barge-in, termination metadata, three-second text closing, and a follow-up that restarts the timer.

### Future Improvements

Use telephony provider events for authoritative hang-up state, configurable channel-specific grace periods, and metrics for interrupted/abandoned closes.

### Lessons Learned

“Goodbye” is communication; termination is a state transition. Both must be coordinated.

---

## 5.4 Job-Loss Hardship and Premium Hold

### Overview

The job-loss workflow offers an eligible two-month premium hold, keeps configured benefits active, generates a hold reference, sends confirmations, and closes by customer name.

### Problem

Hardship originally led to generic payment options or premature specialist transfer. Accepted holds could lack a generated reference, tool persistence, SMS/email records, or correct confirmation state.

### Root Cause

- hardship was treated as general negotiation;
- hold eligibility existed in data but was not a complete workflow;
- response strings could imply a hold without tool execution;
- confirmation and closing were not connected to the hold tool chain.

### Workflow Before

```text
Job loss -> generic options -> possible transfer
```

### Workflow After

```text
Verified customer
  -> job-loss detection and empathy
  -> load eligible premium-hold program
  -> offer configured hold
  -> customer accepts
  -> premium_hold_create
  -> sms_confirmation_send
  -> email_confirmation_send
  -> reference confirmation
  -> named closing
```

### Architecture Changes

- Added policy-backed assistance program selection.
- Added staged hold state and response classification.
- Added tool chaining and persistent reference generation.
- Added deterministic fallback wording and LLM factual constraints.

### Nodes Changed

`NegotiationClassificationNode`, `PrePlanIntentNode`, `ExecutionPathIntentNode`, `PlanProposalDirectiveNode`, `CollectionReactNode`, `PlanProposalGraphNode`, and `CollectionResponseNode`.

### State Changes

| Variable | Example progression |
|---|---|
| `hardship_context` | `{hardship_detected: true, hardship_reason: job_loss}` |
| `hardship_hold_stage` | `offered -> accepted -> created -> sms_sent -> confirmed` |
| `hold_response` | `accepted`, `uncertain`, `rejected` |
| hold details/reference | `HOLD-...`, months, active-benefits flag |

### Tools

`premium_hold_create -> sms_confirmation_send -> email_confirmation_send`.

### Runtime Files

`premium_holds.json`, `sms_confirmations.json`, `email_confirmations.json`, `dispositions.json`, and state/tool logs.

### Verification and Testing

Tests verify hold persistence, the three-tool chain, accepted-hold routing, guarded wording, dynamic reference, and customer-specific closing.

### Future Improvements

Connect the real policy administration platform, approval service, customer notification providers, and idempotent hold cancellation/revision.

### Lessons Learned

Empathy selects the communication style; policy and tools select the actual assistance.

---

## 5.5 Installment Discount, Standard Options, and Human Transfer

### Overview

When a customer is unsure about paying after the hold, the workflow evaluates a configured installment discount. Rejection leads to verified standard options, followed by human transfer only if no automated option is suitable.

### Problem

The agent repeated the hold, offered generic partial payment too early, confirmed the hold after discount acceptance, repeated the discount after confirmation, invented a combined hold-plus-discount offer, or created an unsupported installment plan.

### Root Cause

- uncertainty after a hold was not a distinct state;
- stale hold state remained active during discount confirmation;
- the model had enough freedom to invent products;
- discount rejection and counter-offer language were not consistently classified;
- escalation and transfer were not explicit workflow outcomes.

### Workflow Before

```text
Hold unsuitable -> generic options/repeated hold/random LLM offer
```

### Workflow After

```text
Hold uncertain/rejected
  -> installment_discount_evaluate
  -> present eligible configured discount
       -> accepted: apply -> SMS -> email -> review follow-up -> confirm
       -> rejected/counter: explain configured standard options
            -> still unsuitable: human_escalation -> transfer pending
```

### Architecture Changes

- Added rules-first classification for hold uncertainty and discount response with LLM fallback.
- Added planner guardrails from post-hold uncertainty to discount evaluation.
- Added discount evaluation/application tools and structured revised amount.
- Added unsupported-offer validation in the response layer.
- Added human escalation state and transfer objective.

### Nodes Changed

`NegotiationClassificationNode`, `ExecutionPathIntentNode`, `PlanProposalDirectiveNode`, `CollectionReactNode`, `PlanProposalGraphNode`, and `CollectionResponseNode`.

### State Changes

| Variable | Role |
|---|---|
| `post_hold_capacity` | Ability after the hold |
| `discount_stage` | `requested`, `offered`, `accepted`, `applied`, `confirmed`, `counter_offer`, `rejected` |
| `discount_response` | Customer reaction |
| `generic_options_offered_after_discount` | Ensures standard options precede transfer |
| `human_escalation_status` | Queued/completed escalation |
| `human_transfer_status` | Pending/transferring/transferred |
| `final_disposition` | Final discount or escalation result |

### Tools

```text
installment_discount_evaluate
  -> installment_discount_apply
  -> sms_confirmation_send
  -> email_confirmation_send
  -> followup_schedule (configured review)

or

human_escalation -> transfer response
```

### Runtime Files

`installment_discounts.json`, `sms_confirmations.json`, `email_confirmations.json`, `followups.json`, `escalations.json`, `discount_handoffs.json`, and dispositions.

### Verification and Testing

Tests cover rule/LLM uncertainty, discount lifecycle, counter requests, standard options before handoff, no mixed offer, no repeat after confirmation, escalation, and plan synchronization.

### Future Improvements

Add real approval matrices, specialist routing, service-level tracking, offer-expiry handling, and a versioned policy decision audit.

### Lessons Learned

LLM creativity must stop at the boundary of approved financial products.

---

## 5.6 Partial-Payment Lifecycle

### Overview

The partial-payment workflow captures a current amount, validates the account-specific minimum, creates a secure link, sends confirmation, tracks the remaining balance, and closes correctly.

### Problem

The agent could miss fractions such as “half,” accept an amount below policy, repeat the amount question without explanation, claim a link before tool execution, or fail to track the remaining balance.

### Root Cause

- amount extraction, policy validation, and workflow stages were not connected;
- validation details did not reach response rendering;
- stale capacity from a previous turn could be reused;
- link offer and link creation were not separate stages.

### Workflow Before

```text
Partial intent -> generic amount question -> uncertain outcome
```

### Workflow After

```text
Partial-payment intent
  -> collect/normalize amount
  -> validate allow_partial_payment and min_partial_payment_pct
       -> invalid: explain verified threshold and request valid amount
       -> valid: offer link
  -> payment_link_create
  -> sms confirmation
  -> confirm amount, reference, remaining balance
  -> named closing
```

### Architecture Changes

- Added shared amount normalization utilities outside the graph-node package.
- Added structured `partial_payment_validation` context.
- Added lifecycle stages and link tool orchestration.
- Added response validation against premature link/payment claims.

### Nodes Changed

`CollectionEntityExtractNode`, `NegotiationClassificationNode`, `PrePlanIntentNode`, `ExecutionPathIntentNode`, `PlanProposalDirectiveNode`, `CollectionReactNode`, `PlanProposalGraphNode`, and `CollectionResponseNode`.

### State Changes

`payment_commitment_type=PARTIAL_PAYMENT`, `partial_payment_stage`, `partial_payment_details`, `partial_payment_validation`, `customer_payment_capacity`, `customer_payment_capacity_pct`, and `followup_status`.

### Tools

`payment_link_create` followed by configured confirmation/disposition handling.

### Runtime Files

`payment_links.json`, `sms_confirmations.json`, `dispositions.json`, conversation state, and tool logs.

### Verification and Testing

Tests cover quarter/half normalization, stale amount rejection, below-minimum reasoning, full-versus-partial distinction, link creation, balance response, confirmation completion, and plan state.

### Future Improvements

Integrate a real payment gateway, payment-status webhook, link expiry/resend, PCI controls, and ledger reconciliation.

### Lessons Learned

Remaining on the same objective after validation failure should produce a reasoned correction, not a repeated generic question.

---

## 5.7 Full-Payment Lifecycle

### Overview

The full-payment workflow recognizes immediate full-payment intent, offers a secure method, creates a payment link, returns a tool-generated reference, records the disposition, and offers auto-pay.

### Problem

Immediate payment intent previously fell into generic negotiation. Link messages could be repeated, tool completion was not guaranteed, and the outcome lacked a consistent `PAID_IN_FULL` disposition.

### Root Cause

- commitment type and payment stage were incomplete;
- payment willingness and actual link creation were conflated;
- acknowledgement after confirmation could reopen the workflow;
- auto-pay transition was not connected to full-payment completion.

### Workflow Before

```text
Can pay now -> generic options -> possible link response -> generic close
```

### Workflow After

```text
Full-payment intent
  -> offer payment method
  -> link requested
  -> payment_link_create
  -> confirm amount/reference/receipt behavior
  -> offer auto-pay
  -> close or continue to shared auto-pay workflow
```

### Architecture Changes

- Added rules-first full-payment classification with LLM fallback.
- Added `payment_resolution_stage` and details.
- Reused the existing payment-link tool.
- Added `PAID_IN_FULL` disposition and response completion evidence.

### Nodes Changed

`NegotiationClassificationNode`, `PrePlanIntentNode`, `ExecutionPathIntentNode`, `PlanProposalDirectiveNode`, `CollectionReactNode`, `PlanProposalGraphNode`, and `CollectionResponseNode`.

### State Changes

`payment_commitment_type=FULL_PAYMENT`, `payment_option_response`, `payment_resolution_stage`, `payment_resolution_details`, `final_disposition=PAID_IN_FULL`, and completed confirmation objective.

### Tools

`payment_link_create`, notification handling, and disposition persistence.

### Runtime Files

`payment_links.json`, `sms_confirmations.json`, `dispositions.json`, state, and tool logs.

### Verification and Testing

Tests cover full lifecycle, link/reference, closing, plan progress, and weak LLM classification overridden by deterministic evidence.

### Future Improvements

Add payment-status reconciliation, signed/expiring links, provider idempotency, receipts, and ledger posting.

### Lessons Learned

A commitment to pay and a completed payment action are different workflow states.

---

## 5.8 Reusable Auto-Pay Workflow

### Overview

Auto-pay is implemented as one shared capability reachable through proactive customer request or acceptance of an agent offer after full payment.

### Problem

Proactive auto-pay was not recognized reliably, while post-payment acceptance could close immediately without confirmation. Repeated “sure” or “thank you” messages replayed the same payment-and-standing-instruction text.

### Root Cause

- the two entry paths risked separate implementations;
- weak LLM classification could erase rule evidence;
- auto-pay completion was not explicit;
- the response layer did not know confirmation had already been delivered.

### Workflow Before

```text
Proactive request ----> inconsistent path
Payment offer accept -> possible generic closing
```

### Workflow After

```text
Proactive auto-pay request --------+
                                    v
Full payment -> auto-pay offer -> shared auto-pay state
                                    |
                                    v
                        payment link/standing instruction
                                    |
                                    v
                    confirm both -> AUTOPAY_ENABLED -> close
```

### Architecture Changes

- Added regex/rule detection with LLM fallback.
- Converged both entry points into `autopay_setup_requested` and `autopay_stage`.
- Reused the payment-link workflow.
- Added `AUTOPAY_ENABLED` disposition and completion-aware closing.

### Nodes Changed

The same payment nodes as the full-payment workflow: classification, execution-path routing, directive, React, graph projection, and response rendering.

### State Changes

`autopay_response`, `autopay_setup_requested`, `autopay_stage`, payment details, completed confirmation objective, and `final_disposition=AUTOPAY_ENABLED`.

### Tools

The shared `payment_link_create` mechanism carries the current payment and auto-pay enrollment path. In production, a mandate provider would be a separate external integration while remaining inside this workflow.

### Runtime Files

Payment links, dispositions, notifications, conversation state, and tool logs.

### Verification and Testing

Tests cover proactive request, offered-and-accepted auto-pay, weak LLM output, enabled confirmation, repeated acknowledgements, and closing.

### Future Improvements

Add mandate consent, authorization status, revocation, failure retry, debit schedule, and provider webhooks.

### Lessons Learned

Reusable capabilities should have multiple entry points but one state machine and one tool path.

---

## 5.9 Promise-to-Pay and Follow-Up Scheduling

### Overview

The PTP workflow captures a future full-payment date, validates the configured window, persists a `PTP-...` reference, schedules follow-up, confirms the commitment, and closes by name.

### Problem

Vague timing could be treated as a final date, exact ordinals could be missed, invalid dates caused repeated questions, and the existing promise tool was not fully integrated with follow-up scheduling.

### Root Cause

- payment-later intent and exact promised date were conflated;
- date extraction did not always respect the current objective;
- `max_promise_days` was not consistently propagated to routing/response;
- promise capture and follow-up were not a complete tool chain.

### Workflow Before

```text
Pay later -> generic amount/date question -> no guaranteed operational record
```

### Workflow After

```text
Future-payment intent
  -> ask exact date
  -> parse/normalize date
  -> validate max_promise_days
       -> invalid: explain window and ask earlier date
       -> valid: promise_capture
  -> followup_schedule
  -> PTP confirmation/reference
  -> named closing
```

### Architecture Changes

- Added hybrid PTP classification and stage preservation.
- Distinguished vague timing from exact date capture.
- Integrated policy-window validation.
- Restored/reused `followup_schedule` through `tools/common.py` chaining.
- Added PTP response objectives and plan projection.

### Nodes Changed

`CollectionEntityExtractNode`, `NegotiationClassificationNode`, `PrePlanIntentNode`, `ExecutionPathIntentNode`, `PlanProposalDirectiveNode`, `CollectionReactNode`, `PlanProposalGraphNode`, and `CollectionResponseNode`.

### State Changes

| Variable | Example |
|---|---|
| `payment_commitment_type` | `PROMISE_TO_PAY` |
| `promise_stage` | `date_required -> date_captured -> recording -> captured -> followup_scheduled -> confirmed` |
| `promised_date` | ISO date |
| `promise_date_rejection_reason` | `outside_max_promise_window` |
| `promise_id` | `PTP-...` |
| `final_disposition` | `PROMISE_TO_PAY_SCHEDULED` |

### Tools

`promise_capture -> followup_schedule`, with disposition/state update after successful execution.

### Runtime Files

`promises.json`, `followups.json`, `dispositions.json`, state, and tool logs.

### Verification and Testing

Tests cover vague timing, exact date, latest-turn precedence, preserved waiting state, out-of-range date, persisted promise/follow-up, confirmation, named closing, and regression against verification false positives.

### Future Improvements

Use a production scheduler, timezone/calendar service, reminder provider, promise revisions, broken-promise processing, and CRM integration.

### Lessons Learned

Intent extraction may identify “pay later,” but only validated entity capture can create a financial commitment.

---

## 5.10 Wrong-Party Privacy-Safe Callback

### Overview

When someone other than the policyholder answers, the agent shares no account details, requests a safe callback time, schedules the callback, confirms it, and closes.

### Problem

The agent repeated the same privacy message, treated callback time as a generic acknowledgement, went to dues disclosure despite skipped verification, or confirmed without scheduling.

### Root Cause

- wrong-party state and callback stage were not consistently preserved;
- time extraction and scheduling routes were disconnected;
- response repetition was used instead of objective progression;
- the plan tree followed the normal account branch.

### Workflow Before

```text
Wrong party -> repeated privacy/callback question -> uncertain scheduling
```

### Workflow After

```text
Wrong party detected
  -> privacy notice, no account details
  -> request callback time/message
  -> outbound_callback_schedule
  -> callback reference confirmation
  -> close

Verification and account-detail objectives are skipped.
```

### Architecture Changes

- Added explicit wrong-party callback stages.
- Reused callback time extraction and durable queue.
- Added revision and cancellation handling.
- Added response constraints that prevent account disclosure.

### Nodes Changed

Early intent/routing nodes, `ExecutionPathIntentNode`, `PlanProposalDirectiveNode`, `CollectionReactNode`, `PlanProposalGraphNode`, and `CollectionResponseNode`.

### State Changes

`right_party_status=wrong_party`, `wrong_party_callback_stage`, `wrong_party_callback_time`, callback job ID/time/status, and closing state.

### Tools

`outbound_callback_schedule` and `outbound_callback_cancel` use the shared `OutboundCallbackQueue`.

### Runtime Files

`outbound_callback_jobs.json`, `outbound_call_attempts.json`, conversation state, and tool logs.

### Verification and Testing

Tests cover wrong-party time capture, schedule/cancel selection, confirmation directive, privacy response separation, no repeated notice, timing cleanup, and revised callback confirmation.

### Future Improvements

Add legally reviewed wrong-party scripts, calling-window enforcement, provider status callbacks, and CRM task ownership.

### Lessons Learned

Privacy-safe behavior must remain correct even if the model misunderstands the customer’s wording.

---

## 5.11 Customer-Requested Callback from Any Objective

### Overview

Customers who are busy, driving, or in a meeting can request a callback before or after verification. The workflow suspends the current objective and reuses the existing callback scheduler.

### Problem

“I’m in a meeting” repeatedly triggered a DOB/mobile request. Even after a time was provided, the agent could ask for verification again or close without reference/purpose. The plan tree sometimes marked purpose disclosure done despite no account discussion.

### Root Cause

- verification routing had higher precedence than callback interruption;
- callback stage was populated too late for planning;
- stale verification directives reached the response renderer;
- plan status inferred expected normal flow;
- callback confirmation validation lacked required facts.

### Workflow Before

```text
Busy customer -> verification prompt -> callback request -> verification prompt
```

### Workflow After

```text
Customer busy/callback request
  -> acknowledge without pressure
  -> skip current verification when not completed
  -> ask callback time if missing
  -> schedule through shared queue
  -> confirm time, safe purpose, and CALL reference
  -> named closing
  -> preserve interrupted objective for future continuation
```

### Architecture Changes

- Gave callback interruption precedence in pre-plan/execution routing.
- Added reusable `customer_callback_stage` independent of the originating workflow.
- Added verified response context and callback-specific validation.
- Prevented contact-number leakage and verification requests during scheduling.
- Projected callback status from queue/tool state.

### Nodes Changed

`PrePlanIntentNode`, `ExecutionPathIntentNode`, `PlanProposalStateNode`, `PlanProposalDirectiveNode`, `CollectionReactNode`, `PlanProposalGraphNode`, and `CollectionResponseNode`.

### State Changes

`customer_callback_stage`, `customer_callback_time`, `outbound_callback_job_id`, `outbound_callback_scheduled_for`, `outbound_callback_status`, preserved current objective, and closing state.

### Tools

The same `outbound_callback_schedule` and queue used for wrong-party callbacks. No duplicate scheduler was introduced.

### Runtime Files

Callback jobs/attempts, conversation state/messages, and tool logs.

### Verification and Testing

Tests cover missing-time request, pre-verification callback priority, plan-state selection, verified-customer callback, schedule confirmation, required reference/purpose, and no DOB/mobile prompt.

### Future Improvements

Persist resumable objective checkpoints in CRM and restore them automatically when the callback connects.

### Lessons Learned

Cross-workflow interruptions should be first-class objectives, not special cases duplicated inside every scenario.

---

## 5.12 Objective-Driven LLM Response Rendering and Guardrails

### Overview

Response rendering was strengthened so the LLM receives customer-safe verified context, communicates the current objective naturally, and falls back to deterministic templates when output is invalid.

### Problem

The LLM introduced wording variation that sometimes changed meaning: unsupported installment splitting, invented combined assistance, missing references, generic closings, repeated confirmations, or verification requests during callbacks.

### Root Cause

- the renderer sometimes knew only the objective, not the validation reason/tool evidence;
- broad prompts did not reliably enforce every financial constraint;
- internal state could be exposed without a customer-safe context boundary;
- output validation was incomplete;
- deterministic templates were selected inconsistently.

### Workflow Before

```text
Objective/state -> broad LLM prompt -> response
```

### Workflow After

```text
Objective + verified facts + tool output + latest message + compliance constraints
  -> customer-safe Response Context
  -> LLM rendering
  -> factual/compliance validation
       -> valid: return
       -> invalid/timeout: deterministic fallback
```

### Architecture Changes

- Kept response decisions in `CollectionResponseNode` without moving workflow logic.
- Restricted LLM context to communicable facts.
- Added template selection by objective and state.
- Added validators for references, policy values, callback facts, unsupported offers, privacy, and premature completion.
- Recorded render diagnostics and completion evidence.

### Nodes Changed

Primarily `CollectionResponseNode`; prompts in `agent_prompts.yml`; supporting objective consistency in planner/graph nodes.

### State Changes

Response metadata, verified render variables, validation results, completed objectives, and workflow-specific validation structures.

### Tools

No tool execution is moved into the LLM. Response facts originate from normal tool observations.

### Runtime Files

Conversation messages/state, tool logs, traces, and workflow-specific domain records used as evidence.

### Verification and Testing

Tests cover LLM-first rendering, timeout/failure fallback, invented reference rejection, below-minimum explanation, unsupported split rejection, callback privacy, generic named closing, placeholder blocking, dues-before-verification, and mixed-offer prevention.

### Future Improvements

Add policy-aware response schemas, calibrated LLM judges used only as secondary validation, multilingual templates, and response-quality telemetry.

### Lessons Learned

Prompts improve behavior, but verified context and deterministic validation provide the actual safety boundary.

---

# 6. Runtime Architecture

## 6.1 Purpose of Runtime Persistence

The runtime directory provides prototype persistence and observability. It answers two different questions:

1. **What does the agent currently believe?** This is stored in conversation state and memory.
2. **What action actually occurred?** This is stored in workflow-specific tool records.

A response should not be considered evidence that an action occurred. A tool-backed record and observation provide that evidence.

## 6.2 Fixture Data Versus Runtime Data

```text
agents/collection_agent/data/
  -> stable fixtures and configuration
  -> customers, cases, policies, assistance programs, histories

agents/collection_agent/runtime/
  -> generated execution data
  -> messages, states, tool records, callbacks, traces
```

Generated runtime files were removed from source-control history and cleanup rules were improved. This reduces noisy diffs and the risk of committing customer/session data.

## 6.3 Runtime File Catalog

| Runtime file | What it stores | Why it exists | How it is used later |
|---|---|---|---|
| `conversation_states.json` | Session-level memory and workflow state | Resume/debug multi-turn behavior | Loaded for later turns and UI inspection |
| `conversation_messages.json` | Customer/agent message history | Context, replay, audit | Recent messages support rendering and session analysis |
| `verification_attempts.json` | DOB/mobile verification attempts and status | Compliance evidence and retry state | Prevent disclosure until requirements pass |
| `tool_logs.json` | Tool names, inputs, outputs, errors, timings | Diagnose orchestration | Confirms whether an action was attempted/succeeded |
| `plan_proposals.json` | Persisted plans/proposals | Planning diagnostics | Compare objectives and plan versions |
| `payment_links.json` | Payment amount, link, reference, case/customer, status | Evidence that a link was created | Confirmation, resend, reconciliation prototype |
| `phone_payments.json` | Pay-by-phone records | Alternate payment-channel audit | Payment processing/reconciliation prototype |
| `premium_holds.json` | Hold program, months, reference, status | Evidence of approved hold | Confirmation and future servicing |
| `installment_discounts.json` | Original/revised amount, percentage, reference | Discount audit | Confirmation, reporting, review |
| `discount_handoffs.json` | Discount specialist handoff data | Preserve context for review | Human queue integration prototype |
| `promises.json` | PTP date, amount, reference, status | Customer commitment record | Reminder and broken-promise processing |
| `followups.json` | Scheduled reminders/reviews | Operational continuity | Future scheduler execution |
| `sms_confirmations.json` | SMS delivery requests and references | Notification audit | Provider delivery/retry integration |
| `email_confirmations.json` | Email delivery requests and references | Notification audit | Provider delivery/retry integration |
| `outbound_callback_jobs.json` | Callback job, due time, reason, status, continuation | Durable local scheduler queue | Dispatcher selects due jobs |
| `outbound_call_attempts.json` | Callback provider attempts/results | Retry and audit | Failure analysis and status update |
| `escalations.json` | Human escalation reason, case/customer, status | Handoff evidence | Specialist queue integration |
| `dispositions.json` | Final business outcomes | Analytics and reporting | Workflow completion metrics |
| `contact_attempts.json` | Collection contact attempts | Contact strategy tracking | Attempt limits and reporting |
| `channel_switches.json` | Requested channel transitions | Omnichannel context | Continue workflow on another channel |
| `runtime/traces/*.json` | Node execution, timing, route, response data | Deep engineering observability | Latency and root-cause analysis |

## 6.4 CollectionDataStore

`tools/data_store.py` provides typed helper methods around JSON fixtures and runtime files. It:

- creates the runtime directory;
- initializes required files to `[]`;
- reads fixture and runtime JSON;
- appends domain records;
- saves updated record lists.

This is a repository-like abstraction for the prototype. Tools should use it instead of implementing unrelated file logic.

## 6.5 Callback Queue Reliability

`services/outbound_callback_queue.py` has a specialized queue because callbacks need due-time dispatch, retries, cancellation, expiry, provider references, and attempt history.

Important reliability behavior includes:

- absolute timestamp resolution;
- generated `CALL-...` job IDs;
- temporary-file write followed by replacement;
- failed-attempt recording;
- retry and terminal failure handling;
- cancellation by job or case;
- recovery from malformed JSON by restoring a valid empty list.

## 6.6 Limitations of JSON Persistence

Local JSON is appropriate for development demonstrations but is not production-ready because it lacks:

- robust concurrent writes;
- database transactions;
- distributed locking;
- schema migration;
- access control and encryption;
- indexed queries;
- retention and deletion policies;
- high availability and backups;
- exactly-once/idempotent processing.

Production migration should preserve the repository/tool interfaces while replacing storage implementations.

---

# 7. State Machine Design

## 7.1 Conversation State

Conversation state contains user/session context and lifecycle metadata, including:

- `user_id`, `case_id`, `channel`, and source;
- conversation history;
- opening and right-party status;
- closing/completion/termination state;
- response metadata and call summary.

It answers: “Where is this conversation and can it continue?”

## 7.2 Graph State

`CollectionGraphState` is the per-execution LangGraph contract. It includes:

- namespaced intent results;
- extracted entities;
- tool observations/errors;
- previous/next node and node history;
- active context and verification evidence;
- plan proposal and conversation plan;
- workflow and response fields.

It answers: “What data do graph nodes exchange during this turn?”

## 7.3 Workflow State

Workflow state models business progression. Each workflow has a commitment type and/or stage:

| Workflow | Main state |
|---|---|
| Verification | `identity_verified`, verified/missing fields |
| Wrong-party callback | `right_party_status`, `wrong_party_callback_stage` |
| Customer callback | `customer_callback_stage`, callback job status |
| Premium hold | `hardship_hold_stage`, `hold_response` |
| Discount | `discount_stage`, `discount_response`, offer details |
| Partial payment | `partial_payment_stage`, details, validation |
| Full payment | `payment_commitment_type`, `payment_resolution_stage` |
| Auto-pay | `autopay_response`, `autopay_stage` |
| Promise-to-pay | `promise_stage`, promised date/reference |
| Escalation | `human_escalation_status`, `human_transfer_status` |
| Closing | `conversation_closing`, `conversation_complete`, `terminate_call` |

It answers: “What business objective is active, and which transitions are legal?”

## 7.4 State Transition Example

```text
Customer: "I can pay half."

Before
  payment_commitment_type = NONE
  partial_payment_stage = ""

Classification
  payment_commitment_type = PARTIAL_PAYMENT
  normalized amount = overdue_amount * 0.5

Validation
  partial_payment_stage = link_offered (if policy passes)

Tool execution
  partial_payment_stage = link_created
  partial_payment_details.payment_reference_id = PAY-...

Confirmation
  partial_payment_stage = confirmed
  completed_objectives += partial_payment_confirmation
```

## 7.5 Routing and Conditional Edges

LangGraph conditional edges select execution paths using route methods. The important distinction is:

- routing chooses the next executable graph node;
- workflow state chooses the business objective;
- the plan tree visualizes objective progress;
- response rendering communicates the chosen objective.

These concepts must align but should not be collapsed into one function.

## 7.6 State Precedence

Short replies require prior-state precedence. Examples:

- “yes” after a hold offer means hold acceptance;
- “yes” after an auto-pay offer means auto-pay acceptance;
- “the 30th” while `promise_stage=date_required` is a date answer;
- “sure” after confirmation is an acknowledgement, not renewed acceptance;
- “call at 9 PM instead” during closing is a material callback revision.

The classifier merges current text with prior workflow state, but completed stages are protected from reopening.

## 7.7 Plan Tree

The plan tree uses nodes, edges, a current node ID, next nodes, step markers, timeline snapshots, and revision history. It shows customer-facing objectives, not every LangGraph implementation node.

Correct synchronization should follow:

```text
runtime workflow state
  + completed objectives
  + tool observations
  + disposition
  + verification evidence
       |
       v
plan status projection
```

The current implementation dynamically calculates statuses over a canonical topology. The future direction is a dynamic execution tree that contains only actual and confirmed objectives/transitions.

## 7.8 Reflection State

Reflection uses fields such as:

- `reflection_retry_count`;
- `reflection_plan_retry_count`;
- `reflection_feedback`;
- `reflection_complete`;
- `failure_type`;
- `correction_hints`;
- `retry_target`;
- `plan_validation_warnings`.

These fields support bounded correction. They must not silently turn model feedback into an approved financial decision.

## 7.9 Avoiding Duplicate State

New flags should be added only when existing state cannot represent the required distinction. Duplicate booleans make contradictions possible. Preferred order:

1. reuse a typed workflow stage;
2. derive status from tool output/disposition;
3. use completed-objective history;
4. add a new field only for a genuinely new business fact.

---

# 8. Tool Architecture

## 8.1 Tool Design

Tools extend a shared base tool contract and use Pydantic schemas from `tools/schemas.py`. They isolate side effects from language-model reasoning.

Each tool should be:

- deterministic for the same valid input where possible;
- typed;
- independently testable;
- explicit about persistence;
- safe to retry or protected by idempotency;
- observable through structured output;
- incapable of relying on generated customer-facing prose.

## 8.2 Tool Registry and Execution

The agent registers active tools during initialization. `CollectionReactNode` proposes a tool call, and `ToolExecutionNode` resolves the registered tool, validates arguments, executes it, and writes the observation back into graph state.

```text
Tool call request
  -> registry lookup
  -> schema validation
  -> execute
  -> runtime persistence
  -> typed output
  -> normalized observation
  -> React follow-up decision
```

## 8.3 Tool Catalog

| Tool | Purpose | Main inputs | Main outputs | Persistence |
|---|---|---|---|---|
| `entity_extract` | Generic structured entity extraction | customer text/schema | extracted entities | graph state |
| `verification_entity_extract` | Extract DOB/mobile candidates | customer message | verification entities | graph state |
| `verification_memory_verify` | Reconcile verification evidence with memory | fields/memory | verification result | memory/state |
| `verify_dob` | Verify DOB for customer | customer ID, DOB | matched/status | `verification_attempts.json` |
| `verify_mobile` | Verify registered mobile | customer ID, mobile | matched/status | `verification_attempts.json` |
| `loan_policy_lookup` | Retrieve account policy | loan ID | promise/partial/waiver/restructure rules | fixture read |
| `offer_eligibility` | Evaluate offer eligibility | case/product/hardship context | allowed/recommended next | state/tool observation |
| `payment_link_create` | Create secure payment link/reference | case/customer, amount, type | URL, `PAY-...`, status | `payment_links.json` |
| `promise_capture` | Persist PTP commitment | case, date, amount | `PTP-...`, status | `promises.json` |
| `followup_schedule` | Schedule reminder/review | case/customer, time, reason | follow-up ID/status | `followups.json` |
| `premium_hold_create` | Apply eligible premium hold | case/customer, program, months | `HOLD-...`, status | `premium_holds.json` |
| `installment_discount_evaluate` | Check discount eligibility/terms | account, hardship, amount | eligibility, percentage, revised amount | observation |
| `installment_discount_apply` | Persist approved discount | case/customer, amount, percentage | `DISC-...`, revised amount | `installment_discounts.json` |
| `sms_confirmation_send` | Record/send SMS confirmation | customer/mobile, reference, message type | delivery/status | `sms_confirmations.json` |
| `email_confirmation_send` | Record/send email confirmation | customer/email, reference, message type | delivery/status | `email_confirmations.json` |
| `outbound_callback_schedule` | Create callback job | customer/case/time/reason/context | `CALL-...`, scheduled time, status | callback queue JSON |
| `outbound_callback_cancel` | Cancel queued callback | job ID or case ID | cancelled IDs/status | callback queue JSON |
| `human_escalation` | Queue specialist review/transfer context | case/customer/reason/context | escalation ID/status | `escalations.json` |
| `plan_propose` | Persist a plan proposal | case/objective/steps | plan ID/status | `plan_proposals.json` |

Additional schemas exist for contact attempts, dispositions, channel switching, phone payment, payment status, strict scripts, and summaries. Some represent future/archived framework capabilities and should be registered only when the active workflow uses them.

## 8.4 Tool Chaining

Tool chains are controlled by workflow state and observations. Examples:

```text
premium_hold_create
  -> sms_confirmation_send
  -> email_confirmation_send
```

```text
installment_discount_evaluate
  -> installment_discount_apply
  -> sms_confirmation_send
  -> email_confirmation_send
  -> followup_schedule
```

```text
promise_capture
  -> followup_schedule
```

The next tool should not be selected because a response template mentions it. It should be selected because the previous tool’s structured result and workflow stage require it.

## 8.5 Error Handling

Tool failures should:

- appear in `tool_errors` and observations;
- avoid marking the business stage complete;
- produce a safe retry or escalation objective;
- not allow the response to claim success;
- use idempotency in production to prevent duplicate actions.

## 8.6 Tool Security

Production tool execution requires:

- least-privilege credentials;
- secret management;
- input validation and PII minimization;
- authorization by customer/case;
- immutable audit events;
- rate limits and retry budgets;
- idempotency keys;
- provider signature verification;
- encrypted persistence and transport.

---

# 9. Technical Learnings

## 9.1 LangGraph

- Graph nodes should have narrow responsibilities.
- Conditional edges make control flow explicit and testable.
- Cycles are useful for tools and verification but require clear terminal conditions.
- Typed state is essential for maintainability.
- The graph execution path and the business objective path are related but different.

## 9.2 Large Language Models

- An LLM is strong at ambiguous language understanding and natural communication.
- It is not a reliable policy engine or transaction system.
- Structured output improves integration but can fail or return incomplete JSON.
- Small model/provider changes can affect latency and schema reliability.
- Deterministic fallback and bounded retries are production requirements.

## 9.3 Prompt Engineering

- A prompt cannot compensate for missing state.
- Prompts should describe the model’s responsibility and prohibited behavior.
- Verified structured context is more reliable than large internal-state dumps.
- Examples help tone and formatting but should not become hidden scenario routing.
- Output validation is required for consequential customer communication.

## 9.4 Tool Calling

- Tools define the boundary between reasoning and action.
- A generated reference must come from a tool.
- Tool outputs should be structured and persisted before confirmation.
- Tool chains require explicit stages and retry safety.

## 9.5 Workflow Design

- Workflows should be capability-driven, not scenario-script-driven.
- Multiple entry points should converge into shared state machines.
- Accepted, rejected, uncertain, and counter-offer are distinct states.
- Completion evidence prevents repeated workflows.
- Interruptions such as callbacks should suspend and later resume objectives.

## 9.6 Business Rules

- Rules belong in policy/configuration or a policy service.
- Response generation may explain a verified decision but must not make it.
- Financial options need eligibility, approval, persistence, and audit.
- Privacy must be enforced before information enters response context.

## 9.7 Debugging

- Reproduce exact conversations.
- Inspect graph hops before prompts.
- Compare state before/after.
- Check tool logs and runtime records.
- Use plan-tree discrepancies as a signal, not as the only evidence.
- Measure reflection and retry latency.

## 9.8 Production AI Systems

Production quality is not only response quality. It includes state correctness, policy compliance, tool reliability, privacy, observability, recovery, idempotency, latency, and regression evaluation.

---

# 10. Challenges Faced

## 10.1 Repeated Responses

**Challenge:** Hold, discount, callback, PTP date, and auto-pay confirmations repeated.  
**Engineering finding:** Repetition usually came from an unchanged workflow stage or missing completion evidence, not from vocabulary alone.  
**Resolution:** Model explicit stages, protect terminal stages, record completed objectives, and render from current state.

## 10.2 Ambiguous Short Replies

**Challenge:** “Yes,” “no,” “sure,” and “not sure” are context-dependent.  
**Resolution:** Combine rules with prior workflow state, then use LLM fallback only when needed. Prevent generic acknowledgement from overwriting a stronger active-stage interpretation.

## 10.3 Unsupported LLM Offers

**Challenge:** The model invented combined hold/discount or installment-splitting options.  
**Resolution:** Restrict customer-safe context, expose only verified policy options, validate outputs, and fall back to deterministic templates.

## 10.4 Plan Tree Out of Sync

**Challenge:** UI status disagreed with response and tool execution.  
**Resolution:** Move toward centralized runtime projection and remove completion mutation from unrelated layers. Keep the remaining static-topology limitation documented.

## 10.5 Entity Extraction Versus Workflow Intent

**Challenge:** “End of month” was treated as an exact promise, while “the 4th” could be missed.  
**Resolution:** Separate intent collection from exact-entity collection, use objective context, normalize only when the workflow is waiting for that entity, and validate policy before acting.

## 10.6 Structured Output Failures and Latency

**Challenge:** Some models returned incomplete JSON or took several minutes through retries.  
**Resolution:** Increase appropriate token limits where necessary, use strict structured output with bounded retry/recovery, rely on deterministic rules for clear cases, and inspect node timings.

## 10.7 Closing and Concurrent Input

**Challenge:** A late or revised customer message arrived while closing or after an older request was still running.  
**Resolution:** Latest-input-wins suppression, a short closure grace period, interruption classification, and explicit termination metadata.

## 10.8 Runtime JSON Corruption

**Challenge:** Invalid/corrupt JSON could block queue processing.  
**Resolution:** Atomic callback queue writes, recovery behavior, initialization, tests, and a future database/queue migration plan.

---

# 11. Production Readiness

## 11.1 Components with Strong Production-Oriented Design

- modular LangGraph node responsibilities;
- explicit typed graph state;
- hybrid deterministic/LLM understanding;
- configuration-backed policies and assistance programs;
- Pydantic tool contracts;
- tool-backed references and actions;
- workflow-specific stages and dispositions;
- response validation and deterministic fallback;
- privacy gating;
- callback retries/cancellation/attempt records;
- focused regression tests;
- runtime traces and plan diagnostics.

These are production-oriented patterns, but their current local implementations should not be described as fully production-deployed.

## 11.2 Mocked or Prototype Components

- local JSON as database;
- local callback queue;
- SMS and email confirmation providers;
- payment gateway and payment-status reconciliation;
- auto-pay mandate provider;
- policy administration integration;
- CRM/customer system of record;
- human specialist queue and live call transfer;
- follow-up/reminder scheduler;
- some telephony/provider behavior.

## 11.3 Required Production Services

### Database

Use a transactional relational or event-backed store with schema migration, encryption, indexes, retention, and audit history.

### Queue and Scheduler

Use Redis-backed workers or a managed queue/scheduler with distributed locks, retry policies, dead-letter queues, and idempotency.

### Real Communications

Integrate approved SMS, email, and telephony providers. Track accepted, delivered, failed, bounced, and retried states.

### Payment and Mandates

Use PCI-compliant payment links, signed callbacks, webhook verification, ledger reconciliation, mandate consent, and revocation.

### Monitoring and Alerting

Monitor node latency, LLM retries, structured-output failures, tool error rate, queue backlog, provider failures, privacy violations, workflow drop-off, and disposition distribution.

### Audit and Security

Implement RBAC, secret management, PII minimization, encryption at rest/in transit, immutable audit logs, retention/deletion policies, and security reviews.

### Reliability

Add idempotency to all side-effecting tools, circuit breakers, timeout budgets, fallback models, safe retries, disaster recovery, and reconciliation jobs.

### Scalability

Separate stateless graph workers from durable memory and queues. Partition work by session/case and prevent simultaneous conflicting updates.

## 11.4 Production Readiness Checklist

| Area | Current status | Required next step |
|---|---|---|
| Graph orchestration | Implemented prototype | Load/performance testing |
| Workflow state | Implemented | Typed sub-state migration and concurrency strategy |
| Policy | JSON-backed | Versioned policy decision service |
| Tools | Typed/local | Real provider adapters and idempotency |
| Persistence | Local JSON | Transactional database |
| Queue | Local durable file | Managed distributed queue |
| Observability | Local traces/UI | Central logs, metrics, traces, alerts |
| Security | Development environment | Enterprise IAM, encryption, secrets, PII review |
| Testing | Strong focused tests | Automated end-to-end evaluation pipeline |

---

# 12. Future Roadmap

## 12.1 Short-Term

- Commit and stabilize the runtime plan projection changes.
- Resolve remaining broad regression failures.
- Add explicit typed state fields for dynamically stored workflow values.
- Add idempotency guards to local side-effecting tools.
- Improve provider-independent date/time parsing and currency formatting.
- Redact PII from traces and logs.
- Build a canonical conversation regression dataset from verified sessions.

## 12.2 Medium-Term

- Replace runtime JSON with repository interfaces backed by a database.
- Replace the callback/follow-up files with a managed scheduler.
- Integrate real SMS, email, telephony, payment, and CRM APIs.
- Persist resumable workflow checkpoints for callbacks/channel switches.
- Introduce versioned policy decisions and approval workflow.
- Implement a dynamic execution-only objective tree.
- Add dashboards for workflow completion, privacy, latency, and tool reliability.

## 12.3 Long-Term

- Deploy an enterprise event-driven architecture with auditable workflow events.
- Add automated next-best-action and risk models behind policy constraints.
- Support multilingual voice conversations with locale-specific compliance.
- Add human-in-the-loop review and specialist-assignment optimization.
- Implement continuous agent evaluation and model/prompt release gates.
- Add drift detection for intents, tool selection, and conversation outcomes.

---

# Agent Evaluation and Regression Testing

## My Learnings and Future Direction

This chapter describes my learnings and proposed future direction. It does **not** claim that the complete evaluation platform described below has already been implemented in the Collection Agent.

While working on the agent, I learned that manual conversations are necessary for debugging but insufficient for production assurance. A collection agent can produce a fluent response while selecting the wrong workflow, skipping a tool, violating policy, leaking private details, or corrupting state. Evaluation must therefore measure the complete trajectory, not only the final text.

## Why Agent Evaluation Is Important

Traditional language-model evaluation often compares one prompt with one answer. An agent interacts with state, tools, policies, queues, and users over multiple turns. Its quality depends on whether it:

- understands the customer;
- selects the correct objective;
- follows legal state transitions;
- invokes the correct tool with correct arguments;
- handles tool failure;
- obeys privacy and financial policy;
- persists the correct result;
- communicates only verified facts;
- completes or transfers the workflow;
- remains stable after model, prompt, or code changes.

A strong final response cannot compensate for an incorrect discount application. Similarly, a correct tool call does not guarantee a compliant customer explanation. Evaluation needs separate dimensions for understanding, trajectory, action, state, and response.

## Regression Testing for AI Agents

Regression testing answers: “Did a code, prompt, model, policy, or provider change break behavior that previously worked?”

Unlike deterministic software, LLM outputs may vary. Tests should therefore combine:

- exact checks for deterministic business facts;
- schema checks for structured output;
- state-transition assertions;
- tool-name and argument assertions;
- policy invariants;
- semantic/rubric checks for response quality;
- repeated runs to measure variance;
- latency and token/cost thresholds.

### Regression Test Layers

| Layer | Example assertion |
|---|---|
| Unit | `promise_capture` writes one valid PTP record |
| Node | Hold uncertainty becomes `discount_stage=requested` |
| Graph | Valid PTP date reaches `ToolExecutionNode` |
| Workflow | Discount rejection shows standard options before escalation |
| Policy | ₹7,000 is rejected when the configured minimum is ₹7,560 |
| Response | Rejection explains the verified minimum without inventing terms |
| End-to-end | Conversation reaches correct disposition and closes |
| Non-functional | P95 turn latency stays below target |

## Conversation Replay

A replay dataset should contain realistic multi-turn conversations with expected checkpoints. Each case should include:

- customer/case fixture;
- policy version;
- ordered customer messages;
- expected intent per turn;
- expected objective per turn;
- expected state diff;
- expected tool calls and forbidden tool calls;
- expected disposition;
- response constraints;
- privacy and policy labels.

Example replay specification:

```yaml
case_id: partial_below_minimum_then_valid
customer: CUST-2002
turns:
  - user: "I can pay 7000 today"
    expect:
      commitment_type: PARTIAL_PAYMENT
      partial_payment_stage: amount_invalid
      validation_reason: below_minimum_partial_payment
      forbidden_tools: [payment_link_create]
  - user: "I can increase it to 8000"
    expect:
      partial_payment_stage: link_offered
      offered_amount: 8000
```

Replay makes bugs reproducible and allows old production sessions to become future regression tests after anonymization and review.

## Workflow Validation

Workflow validation checks that the sequence of objectives is legal. It should verify both positive and negative paths.

Examples:

- purpose disclosure cannot occur before successful verification unless the approved callback script permits a safe generic purpose;
- discount application cannot occur before eligibility evaluation;
- payment confirmation cannot occur before link/tool evidence;
- PTP confirmation requires a valid date, promise record, and follow-up;
- specialist transfer follows configured automated options;
- completed workflows do not reopen on “thank you.”

A transition validator can compare observed objective transitions against an allowed state-machine specification while still allowing cross-workflow interruptions such as callback.

## State Validation

State validation should assert invariants after every turn:

```text
identity_verified == false
  => no account-specific amount/policy details in response context

discount_stage == confirmed
  => discount reference exists and apply tool succeeded

promise_stage == followup_scheduled
  => promise_id exists and follow-up record exists

conversation_complete == true
  => no non-closing objective remains in progress
```

State diff scoring should measure whether required fields changed, forbidden fields remained unchanged, and terminal fields are internally consistent.

## Tool Validation

Tool evaluation should examine:

- tool selection accuracy;
- argument correctness;
- ordering;
- unnecessary calls;
- missing calls;
- duplicate calls;
- error recovery;
- persisted output;
- idempotency;
- whether the response accurately reflects the result.

For example, auto-pay acceptance should not merely produce auto-pay wording. The evaluation should check that the shared workflow was entered, required link/mandate metadata was produced, disposition was updated, and confirmation occurred exactly once.

## Policy Compliance

Policy tests should derive expectations from versioned configuration rather than hardcoded conversation strings. Important invariants include:

- minimum partial-payment percentage;
- maximum promise days;
- eligible hold duration;
- eligible discount percentage;
- approval requirements;
- allowed products/accounts;
- privacy before verification;
- wrong-party non-disclosure;
- calling-window rules;
- escalation conditions.

Adversarial cases should attempt to persuade the model to exceed policy, combine unsupported options, reveal account details, or claim an unexecuted action.

## Hallucination Detection

Hallucination evaluation should compare every consequential response fact with an allowed source:

| Response fact | Required source |
|---|---|
| Customer name | verified customer profile |
| Policy/account number | verified case context after privacy gate |
| Amount and due date | case data |
| Minimum partial amount | policy calculation |
| Discount percentage/revised amount | evaluation/apply tool output |
| Reference number | tool output/runtime record |
| Callback time | normalized scheduler input/output |
| Confirmation sent | successful notification tool observation |

Any unsupported consequential fact should fail the evaluation even if it sounds plausible.

## Benchmarking

Benchmarking should compare models, prompts, and code versions under the same dataset and environment. A useful benchmark matrix is:

| Dimension | Variants |
|---|---|
| Model/provider | current model, candidate model, deterministic fallback |
| Prompt | production prompt, proposed revision |
| Temperature | production setting and controlled alternatives |
| Workflow | verification, callback, hold, discount, partial, full, auto-pay, PTP, transfer |
| Language style | direct, indirect, noisy ASR, mixed language |
| Tool condition | success, timeout, malformed response, retryable failure |
| Policy | multiple loan/product configurations |

Each configuration should run multiple times for stochastic components. Results should report average, variance, and failure categories rather than one overall score.


## Automatic Testing Pipelines

A future continuous evaluation pipeline could be:

```text
Versioned Conversation Dataset
            |
            v
Create Isolated Customer/Policy Fixtures
            |
            v
Run LangGraph Agent (fixed seed/config where possible)
            |
            v
Capture Every Turn
  - graph hops
  - state snapshots and diffs
  - objectives and plan
  - tool calls/outputs
  - response and latency
            |
            v
Deterministic Validators
  - schema
  - policy
  - state invariants
  - tools
  - privacy
            |
            v
Semantic Response Evaluators
  - clarity
  - empathy
  - acknowledgement
  - non-repetition
            |
            v
Aggregate Metrics and Failure Taxonomy
            |
            v
Evaluation Report and Release Gate
```

Recommended CI behavior:

1. Run deterministic unit/node tests on every pull request.
2. Run a small critical conversation suite on every pull request.
3. Run full repeated stochastic evaluation nightly.
4. Compare candidate versus baseline with confidence intervals.
5. Block release on privacy, policy, hallucination, or tool regressions.
6. Store traces for failed cases.
7. Require human review for changed high-risk outcomes.

## Research Papers Studied

### 1. AgentBench

**Paper:** [AgentBench: Evaluating LLMs as Agents](https://arxiv.org/abs/2308.03688)

AgentBench evaluates LLMs as interactive agents rather than static question-answering systems. The paper introduced a multi-dimensional benchmark with eight environments and evaluated 27 API-based and open-source models. Its environments require multi-turn reasoning, decision-making, instruction following, and interaction with external systems. The reported analysis highlights long-horizon reasoning, decision-making, and instruction-following failures as major obstacles for usable agents.

**Relevant ideas:**

- Evaluate complete trajectories, not only final answers.
- Use multiple environments/tasks to avoid overfitting to one interaction style.
- Keep environments repeatable enough for model comparison.
- Categorize failure causes instead of reporting only success rate.
- Measure long-term decision quality across multiple turns.

**Application to the Collection Agent:**

Collection workflows can be treated as task environments: verification, wrong-party callback, hardship, partial payment, full payment, PTP, and transfer. Each environment has state, allowed actions, tool interfaces, and terminal outcomes. An AgentBench-inspired suite would replay many customer utterance styles and score whether the agent completed the correct trajectory while obeying privacy and policy.

The Collection Agent needs stronger domain invariants than general benchmarks. A successful outcome is not enough if the path contained unauthorized disclosure or a fabricated discount. Therefore, AgentBench’s trajectory focus should be combined with financial-policy validation.

### 2. ToolBench / ToolLLM

**Paper:** [ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs](https://arxiv.org/abs/2307.16789)  
**Project:** [OpenBMB ToolBench](https://github.com/OpenBMB/ToolBench)

ToolLLM introduced a framework for data construction, model training, and evaluation around real-world API use. ToolBench provides large-scale tool-use instructions and API interactions, while ToolLLaMA and an API retriever demonstrate how models can select and use APIs. The work makes tool-use evaluation a first-class problem: the model must understand the request, select an appropriate API, construct valid arguments, execute it, interpret observations, and complete the task.

**Relevant ideas:**

- Separate tool retrieval/selection from argument construction and execution.
- Evaluate multi-tool chains, not only one API call.
- Check whether the tool path actually satisfies the user instruction.
- Include tool/API failures and recovery.
- Compare model plans against execution outcomes.

**Application to the Collection Agent:**

The Collection Agent’s tool set is smaller but higher risk. An evaluation should verify:

- `premium_hold_create` is selected only after eligible acceptance;
- `installment_discount_evaluate` precedes application;
- `payment_link_create` uses the correct amount/type;
- `promise_capture` is followed by `followup_schedule`;
- callback schedule/cancel uses the correct job/case/time;
- notification tools use the correct reference;
- no tool runs twice for the same accepted action.

API correctness should include schema validity, business authorization, persisted output, and response consistency.

### 3. ReAct

**Paper:** [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)  
**Project page:** [ReAct](https://react-lm.github.io/)

ReAct interleaves reasoning traces with actions and observations. Reasoning helps the agent form and update plans, while actions allow it to query external sources or environments. The paper evaluated the approach on question answering, fact verification, and interactive decision-making environments, showing that the combination can improve task performance and interpretability compared with reasoning-only or acting-only approaches.

**Relevant ideas:**

- Reasoning and action should inform each other.
- Observations from tools should update the next decision.
- A trajectory can be inspected for error propagation.
- External evidence can reduce unsupported model conclusions.

**Application to the Collection Agent:**

`CollectionReactNode`, `ToolExecutionNode`, and tool observations follow a related reason/action/observation pattern. Evaluation should not require exposure of private chain-of-thought. Instead, it should validate observable process artifacts:

- selected objective;
- selected tool;
- tool arguments;
- tool result;
- next state transition;
- response facts.

Reasoning-path evaluation should focus on structured decisions and outcomes rather than storing or grading hidden model reasoning.

### 4. Reflexion

**Paper:** [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366)

Reflexion proposes improving language agents through verbal feedback and episodic memory rather than updating model weights. After feedback from an environment or evaluator, the agent generates a reflection that can guide a later attempt. The paper evaluates this approach across sequential decision-making, coding, and language reasoning tasks and studies different feedback sources and memory methods.

**Relevant ideas:**

- Convert failure feedback into actionable language guidance.
- Preserve useful feedback across attempts.
- Evaluate recovery, not only first-attempt success.
- Distinguish external feedback from self-generated critique.
- Bound retries to prevent unproductive loops.

**Application to the Collection Agent:**

The project’s `CollectionReflectNode`, retry counters, feedback, correction hints, and retry target have conceptual similarity to reflective correction. A future evaluation should measure:

- whether reflection detects an invalid plan;
- whether it chooses the correct retry target;
- whether the next attempt fixes the specific failure;
- how many retries are required;
- whether latency stays within budget;
- whether reflection ever changes a correct deterministic decision incorrectly.

Unlike a learning agent that stores open-ended reflections, a regulated collection agent should store only safe structured feedback and should not allow reflection to override policy.

### 5. OpenAI Evals

**Framework:** [OpenAI Evals](https://github.com/openai/evals)  
**Guidance:** [Building an eval](https://github.com/openai/evals/blob/main/docs/build-eval.md)

OpenAI Evals is an open-source framework and registry for evaluating models and systems built with models. It supports existing and custom evaluations, private datasets, completion-function abstractions, result recording, and model-graded or programmatic evaluation patterns. It encourages developers to turn application requirements into repeatable datasets and scoring logic so model or prompt changes can be compared systematically.

OpenAI Evals is a framework rather than one research paper, but it is directly relevant to continuous regression testing.

**Relevant ideas:**

- Store evaluation samples as versioned datasets.
- Separate the task/evaluation logic from the model or solver.
- Use exact/programmatic graders where possible.
- Use model graders only for subjective qualities with clear rubrics.
- Compare candidate configurations with a baseline.
- Record per-sample results for failure analysis.

**Application to the Collection Agent:**

The project could define private eval samples containing conversation turns and expected state/tool outcomes. A custom completion/solver adapter would run the LangGraph agent, while deterministic graders would inspect states, tool logs, policy compliance, and dispositions. A calibrated rubric grader could score empathy and clarity after all hard invariants pass.

## Proposed Evaluation Architecture for the Collection Agent

```text
Anonymized Conversation Dataset
             |
             v
Fixture and Policy Loader
             |
             v
Isolated LangGraph Agent Runner
             |
             v
Turn-Level Capture
  + node hops
  + workflow objective
  + state before/after
  + plan projection
  + tool calls/results
  + runtime records
  + response/latency
             |
             v
Validation Engine
  + transition validator
  + state invariant validator
  + tool validator
  + policy/privacy validator
  + hallucination validator
  + response rubric
             |
             v
Metrics Aggregator
             |
             v
Evaluation Report, Trace Links, and Release Gate
```

### Recommended Components

| Component | Responsibility |
|---|---|
| Dataset registry | Version conversations, labels, policies, and expected outcomes |
| Isolated runner | Reset runtime storage and execute each sample reproducibly |
| Trace collector | Capture graph nodes, state snapshots, tools, response, latency |
| Deterministic graders | Evaluate state, tools, policy, privacy, schema, disposition |
| Semantic grader | Evaluate naturalness only after hard checks pass |
| Baseline comparator | Compare candidate model/prompt/code to approved version |
| Report generator | Summaries, KPI trends, failure taxonomy, sample traces |
| CI release gate | Block high-risk regressions automatically |

### Dataset Categories

- happy-path verification and purpose disclosure;
- wrong party and privacy attacks;
- busy customer callbacks at varied times;
- callback revisions/cancellation;
- accepted, uncertain, and rejected premium holds;
- accepted/rejected/counter discount;
- unsupported combined-offer requests;
- partial amounts below, equal to, and above threshold;
- full payment and auto-pay entry paths;
- valid, vague, past, and out-of-window PTP dates;
- tool timeout/failure/retry;
- acknowledgements after confirmation;
- interruption during closing;
- ASR noise, spelling errors, indirect language, and code-switching.

### Release Gates

Suggested non-negotiable gates:

- 100% wrong-party non-disclosure in the critical suite;
- 100% deterministic policy invariant compliance;
- 0 invented references or unexecuted-action claims;
- 100% correct required-tool invocation for critical financial actions;
- no statistically significant regression in workflow completion;
- latency and structured-output failure below agreed thresholds;
- human review of every changed escalation/discount failure category.

## Key Takeaways

- Agent quality must be measured across trajectory, state, tools, policy, and response.
- Deterministic graders should own financial and privacy checks.
- LLM-based evaluation is useful for naturalness but should not replace hard invariants.
- Conversation replay can convert discovered bugs into permanent regression protection.
- Evaluation should compare models/prompts/code against an approved baseline.
- The existing tests and runtime traces form a strong foundation, but a complete continuous evaluation platform remains future work.

## Future Research Directions 

**1. Dynamic Objective Tree Optimization** 

Investigate adaptive objective trees that learn from historical conversation logs and customer outcomes. Rather than relying on static workflows, future agents could dynamically optimize decision paths based on successful interactions, improving efficiency and customer experience. 

**2. Automated Agent Evaluation & Regression Framework**

Develop an automated evaluation pipeline that continuously measures agent performance using predefined test conversations and production scenarios. Evaluation metrics may include intent accuracy, workflow completion, response quality, empathy, policy compliance, hallucination detection, and business KPIs to ensure new changes do not introduce regressions. 

**3. Privacy-Preserving Agent Evaluation** 

Design evaluation methods that validate agent reasoning, policy compliance, and workflow decisions while protecting sensitive customer information. Future work should ensure that evaluation frameworks can assess agent behavior without exposing private conversation content or internal reasoning. 

**4. Robust Voice AI Evaluation**

Study the robustness of conversational agents under real-world voice conditions, including Automatic Speech Recognition (ASR) errors, background noise, different accents, multilingual conversations, and code-switched speech. This will improve reliability for production Voice AI systems. 

**5. Explainable Agent Decision Making** 

Explore techniques for explaining why an AI agent selected a particular workflow, tool, or escalation path. Providing interpretable decision traces can simplify debugging, improve developer trust, and support enterprise governance without revealing private chain-of-thought. 

**6. Failure Attribution Across Agent Components** 

Investigate methods to automatically identify whether failures originate from intent classification, entity extraction, workflow planning, tool execution, state management, or response generation. Component-level attribution would significantly reduce debugging effort and improve system reliability. 

**7. Offline-to-Online Performance Evaluation** 

Develop evaluation frameworks that connect offline benchmark results with anonymized production telemetry. This enables continuous monitoring of model performance after deployment and helps validate whether offline improvements translate into better real-world outcomes. 

**8. Confidence-Aware Human Escalation** 

Research confidence estimation techniques that allow AI agents to determine when they are uncertain about a response or workflow decision. Low-confidence interactions can then be proactively escalated to human specialists, improving customer satisfaction while maintaining operational efficiency. 

**9. Efficient LLM Orchestration** 

Explore architectural optimizations such as LLM call consolidation, deterministic workflow routing, lightweight routing models, adaptive token limits, and parallel node execution to reduce latency while maintaining response quality. These techniques can significantly improve the scalability of production-grade AI agents. 

**10. Business-Aware Agent Optimization**

Investigate optimization strategies that jointly improve technical metrics (latency, workflow accuracy, tool execution) and business KPIs such as resolution rate, containment rate, customer satisfaction, payment conversion, and average handling time. This aligns AI agent performance with real business objectives. 

## References

1. Liu, X. et al. [AgentBench: Evaluating LLMs as Agents](https://arxiv.org/abs/2308.03688), 2023.
2. Qin, Y. et al. [ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs](https://arxiv.org/abs/2307.16789), 2023.
3. OpenBMB. [ToolBench repository](https://github.com/OpenBMB/ToolBench).
4. Yao, S. et al. [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629), ICLR 2023.
5. Yao, S. et al. [ReAct project page](https://react-lm.github.io/).
6. Shinn, N. et al. [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366), 2023.
7. OpenAI. [OpenAI Evals](https://github.com/openai/evals).
8. OpenAI. [Building an eval](https://github.com/openai/evals/blob/main/docs/build-eval.md).

---

**End of handbook**
