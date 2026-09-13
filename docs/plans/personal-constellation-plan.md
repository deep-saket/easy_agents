# Personal Constellation Gap and Delivery Plan

Status: first vertical slice implemented; platform build pending

Branch reviewed: `saket/framework_update`

Repository snapshot: 2026-09-13

## Outcome

This plan extends the [Offline Agent Platform Roadmap](./offline-agent-platform-roadmap.md)
for a single person's home, life-admin, scientific, machine-learning, and startup
work. The existing roadmap remains the source of truth for the runtime. This
document adds:

- a domain and cross-guild Specialist roster;
- the Constellation, Steward, Guild, Liaison, Mission, Playbook, Work order,
  Charter, Gate, Roster, and Control Room vocabulary;
- feature fit analysis and safe Specialist creation;
- the Control Room product model;
- a delivery sequence for personal, scientific, and startup coverage.

The intended end state can contain 100 or more registered Specialists. The
first useful release should have approximately 8–12 working Specialists and a
strong shared runtime. New Charters remain cheap because they reuse capabilities
and graph patterns rather than introducing another bespoke application.

## Repository reality

The repository already has useful graph nodes, LangGraph agents, structured
tools, local/remote model adapters, layered memory, retrieval, observability,
Gmail, WhatsApp, voice, a graph-builder UI, and substantial collection-domain
work. The collection system demonstrates guarded responses, specialist-like
discount delegation, conversation delivery, and scenario evaluation.

It is not yet an agent fleet runtime:

- the package and public import namespace are inconsistent;
- the generic graph and state contracts contain fixed or domain-specific
  assumptions;
- graph-builder output is a placeholder scaffold;
- agent discovery and collection-agent delegation are ad hoc;
- execution is not durable across restarts and has no shared task/event service;
- capabilities do not yet carry centrally enforced permission, effect,
  idempotency, timeout, network, and approval policy;
- strict offline mode is descriptive rather than technically enforced;
- there is no versioned Charter loader, agent lifecycle, canary, quarantine, or
  rollback;
- there is no Control Room for missions, task trees, gates, resources, and
  health;
- the test suite is not fully hermetic or green. The latest broad run excluded
  the explicit live Groq test and produced 244 passes and 30 failures, while a
  nominal unit path still attempted external Groq authentication;
- personal/home, scientific, and startup connectors and policies are mostly
  unimplemented;
- there was no feature intake or draft-Charter service before this slice.

## Gap matrix

| Required behavior | Present foundation | Gap | Planned closure |
| --- | --- | --- | --- |
| One front door | agent and channel examples | no shared Steward runtime | typed supervisor in Mission Runtime phase |
| Overlapping groups | ad hoc agent calls | no Guild membership or Liaison representation | Charter schema and Roster graph |
| Bounded communication | `AgentNode`, collection target strings | no typed Work order, task tree, or delegation budgets | canonical handoff and mission contracts |
| Feature fit | none | no reuse/compose/extend/create decision | offline MVP implemented in `easy_agents.constellation`; harden with registry/evals |
| Automatic agent addition | placeholder agent directories | no generator, validation, lifecycle, or safe activation | draft Charter -> sandbox -> eval -> approval pipeline |
| Capability discovery | tool registry | tools only; no agent/resource/permission metadata | unified Capability registry |
| Durable work | LangGraph without checkpointer | no checkpoint, task queue, schedule, retry, or idempotency | SQLite control store and checkpointer |
| Human control | approval node and collection policies | not universal or durable | policy-enforced executor and resumable Gates |
| Offline guarantee | local model adapters | network fallback is not denied | egress policy plus network-disabled tests |
| Shared memory | substantial memory/retrieval code | namespaces, provenance, retention, and deletion incomplete | memory/knowledge/artifact separation |
| Safe code and automation | coding placeholder and graph scaffold | no filesystem/subprocess sandbox | isolated worker and scoped capability policy |
| Observability | structured trace helpers | no common event lineage or fleet dashboard | event schema, OpenTelemetry export, replay, Control Room |
| Home operations | WhatsApp/voice primitives | no home/device/calendar/bill domain adapters | Home Guild pilot and Home Assistant integration |
| Scientific work | local model/retrieval primitives | no paper, dataset, experiment, or evaluation lifecycle | Science Lab pilot and experiment store |
| Startup work | MailMind and collection examples | no product/customer/engineering/company guild | Venture Studio pilot after core policy/durability |
| Scale beyond one host | local processes | no worker leases, authentication, tenancy, or quotas | local worker pool first; remote workers only after personal profile is stable |

## What this change fills now

The initial vertical slice adds:

- the canonical `easy_agents` namespace for new code;
- versioned `GuildDefinition`, `CapabilityDefinition`,
  `SpecialistDefinition`, and `ConstellationCatalog` contracts;
- a packaged starter Roster containing 9 Guilds, 29 Capabilities, and 16
  Specialists, including multi-Guild Liaisons;
- referential validation for Charter-to-Guild and Charter-to-Capability links;
- deterministic, local feature analysis with four outcomes: reuse, compose,
  extend, and create;
- requested-effect and risk inference;
- explicit approval requirements for payments, outbound communication,
  destructive/device/shell actions, and sensitive identity/medical/legal/tax
  work;
- a non-runnable Draft Charter with no permissions when a new domain is found;
- stable proposal identifiers, explainable matches, and machine-readable next
  steps;
- the `constellation-intake` command and Python API;
- focused tests for Roster validation, overlapping membership, all decision
  paths, sensitive actions, and determinism.

This is intentionally a proposal engine. It does not yet write a Charter into a
persistent Roster, generate a graph, execute a capability, or activate an agent.

## Delivery sequence

Each stage must leave the repository usable and must meet its exit criteria
before the following domain fleet expands.

### Stage 0 — Make the baseline trustworthy

Work:

- classify unit, contract, scenario, integration, GPU, voice, and live tests;
- make default tests network-denied and credential-independent;
- resolve the documented collection, remote-adapter, and dotenv failures;
- ignore or relocate mutable runtime output;
- align distribution name, canonical package name, dependency lock, and CLI;
- add formatting, lint, typing, secret scanning, and a minimal CI matrix.

Exit:

- a clean checkout installs through `easy_agents`;
- the default command passes with no network activity;
- running the examples does not dirty the repository.

### Stage 1 — Establish Charters and the unified Roster

Work:

- evolve the current constellation contracts into `AgentManifest` and
  `CapabilityDescriptor` v1;
- represent models, tools, resources, skills, memory, channels, policy, graph,
  accepted input, output schema, evals, and resource needs;
- merge node, tool, model, channel, and agent lookup behind versioned registries;
- add Charter load, validate, lock, diff, sign, list, and inspect commands;
- make Guild membership many-to-many and compute Liaison status rather than
  granting special authority;
- add lifecycle storage for proposed through retired states.

Exit:

- a Charter can be installed without editing framework core;
- dangling capability, policy, or graph references fail validation;
- inactive/proposed Specialists cannot be selected for a mission;
- the Roster can answer “who can do this, with what effects and permissions?”

### Stage 2 — Harden the Feature Architect and agent factory

Work:

- replace lexical matching with a hybrid of exact tags, schemas, local
  embeddings, and an optional structured local-model judge;
- compare responsibility, capability, permission, memory, data, lifecycle, and
  eval boundaries—not only topic similarity;
- add a fifth recommendation, `create_capability`, beneath the four user-facing
  outcomes when the gap is a tool/integration rather than a Specialist;
- generate a Change Proposal containing Charter/Playbook/capability diffs,
  tests, expected resources, risk, privacy impact, and rollback plan;
- scaffold only inside an isolated workspace;
- generate contract, policy, and scenario-test stubs before implementation;
- build golden feature-routing datasets and false-create/false-reuse metrics;
- require a Gate before installing medium/high-risk changes and before any
  activation;
- add canary runs, promotion, quarantine, rollback, and retirement.

Exit:

- the same request returns a deterministic proposal under a locked catalog;
- known tasks do not create duplicate Specialists;
- unrelated responsibilities are not forced into an over-broad Specialist;
- generated code cannot self-authorize or write the active Roster;
- only an evaluated and approved version can become active.

### Stage 3 — Build the Mission Runtime

Work:

- introduce `RunRequest`, `RunContext`, `AgentResult`, `NodeResult`,
  `WorkOrder`, `ApprovalRequest`, `EventEnvelope`, and `ArtifactRef`;
- separate generic core state from domain extension state;
- compile Sequential, ReAct, Reflect, Plan/Execute, Supervisor, and Map/Reduce
  Playbooks from the same schema used by the UI;
- add SQLite checkpoint, task, event, approval, lease, and schedule services;
- implement cancellation, deadlines, retry, idempotency, deduplication, and
  restart recovery;
- implement permission-narrowing handoffs, recursion/handoff depth, and token,
  tool, time, model, GPU, and monetary budgets;
- run specialists in process first and add isolated local workers for risky or
  resource-heavy work.

Exit:

- a Steward delegates to at least two Specialists and aggregates typed results;
- a killed process resumes without repeating an external side effect;
- cancellation and failures propagate through the task DAG;
- ping-pong delegation terminates deterministically.

### Stage 4 — Enforce policy, privacy, and offline operation

Work:

- make the central Tool Executor the only ordinary side-effect path;
- add read/write/delete/send/network/shell/payment/device effect metadata;
- enforce filesystem roots, command rules, network host allowlists, secret
  references, data labels, and recipient/resource scopes;
- add pre-execution blocking Gates for side effects;
- redact secrets and sensitive personal data in traces and artifacts;
- separate untrusted input from instructions and prevent automatic promotion to
  shared semantic memory;
- add `offline_strict` egress denial with only declared loopback endpoints;
- add encrypted backup, export, deletion, retention, and recovery operations.

Exit:

- every side effect has an auditable policy decision;
- handoffs never receive more permission than their parent;
- strict-offline runs make zero non-loopback calls;
- identity, financial, medical, and legal data obey explicit scopes and
  retention.

### Stage 5 — Build the Control Room

Work:

- implement Today, Constellation, Mission, Roster, Playbooks, Gates, Capability
  Library, Memory Vault, Lab, and Operations views;
- stream correlated mission/task/run/node/model/tool/handoff/approval events;
- show Guild membership, Liaison overlaps, active versus merely registered
  Specialists, resource pressure, and health without implying unrestricted
  agent chat;
- provide pause, resume, approve, deny, cancel, quarantine, rollback, export,
  and forget controls;
- make every high-risk Gate preview the exact action, data, recipient, cost,
  expiry, and reason.

Exit:

- the user can understand why a Specialist was selected and what it can access;
- every running mission exposes its DAG, owner, budget, progress, artifacts,
  and next Gate;
- UI and CLI operate through the same local gateway contracts.

### Stage 6 — Launch the personal foundation and Home Guild

Initial active Specialists:

1. Personal Steward
2. Feature Architect
3. Knowledge Librarian
4. Schedule Coordinator
5. Safety Steward
6. System Operator
7. Household Operator
8. Travel Coordinator
9. Communications Operator
10. Personal Finance Controller in read-only mode

Work:

- calendar, task, notification, local files, email-draft, household inventory,
  bill import, travel research, and Home Assistant adapters;
- recurring routines and event-triggered missions;
- multilingual text/voice entry with an entirely local voice option;
- India-specific fixtures and connector abstractions without hard-coding one
  service provider;
- payment, official-document, medical, tax, and emergency safety evaluations.

Exit:

- one mission can combine household tracking, a reminder, and a notification;
- read-only personal-finance analysis works without exposing credentials;
- no purchase, payment, official submission, message, or device action occurs
  without the configured Gate.

### Stage 7 — Launch the Science Lab

Initial additions:

- Literature Scout/Paper Reader Charter templates over the Knowledge Librarian;
- Citation and Claim Verifier;
- Experiment Designer;
- Data Curator;
- ML Engineer;
- Experiment Runner;
- Evaluation Specialist;
- Scientific Reviewer;
- Technical Writer.

Work:

- scholarly and dataset connectors with provenance;
- local document ingestion, citation graph, and reproducible research memory;
- isolated code execution, CPU/GPU scheduling, dataset/artifact versioning, and
  experiment tracking;
- benchmark, regression, leakage, statistical, robustness, and reproducibility
  checks;
- research-to-product Liaison Playbooks.

Exit:

- a mission can discover sources, design an experiment, run it, evaluate it,
  and produce a traced report;
- every result links its data, code, environment, parameters, metrics, and
  artifacts;
- claims are labeled as sourced evidence, computation, or inference.

### Stage 8 — Launch the Venture Studio

Add Product, Market, Customer Discovery, Engineering, QA, Release, SRE,
Security, Analytics, Growth, Content, Sales, Customer Success, Finance, Legal,
Hiring, People, Fundraising, Partnerships, and Meeting/Decision Charters only as
real workflows require them.

Work:

- company/workspace identity and separate personal/company data scopes;
- product, code-hosting, CI, issue, CRM, support, analytics, document, and
  finance connectors;
- approval-gated outbound communication and release/deployment;
- meeting-to-decision-to-task reconciliation;
- audit, spend, model, worker, and data-retention controls suitable for a small
  team.

Exit:

- personal and company memories cannot leak across scopes;
- a product mission can combine evidence, planning, implementation, evaluation,
  release proposal, and operating metrics;
- customer contact, contracts, hiring decisions, deployment, spend, and public
  publishing remain human-authorized.

### Stage 9 — Scale registrations and workers

Only after the single-user system is stable:

- add remote authenticated workers and resource leases;
- add workspace membership, RBAC, quotas, usage accounting, and tenant tests;
- replace SQLite/DuckDB/local artifact adapters where operational evidence
  justifies it;
- add compatible manifest/schema migrations and in-flight version pinning;
- load-test hundreds of registered Specialists while keeping only bounded
  mission workers active.

Exit:

- 100+ registered Charters do not materially increase idle resource use;
- worker loss, model failure, and compatible upgrades preserve task lineage;
- state, memory, artifacts, traces, tools, and channels pass isolation tests.

## Next six implementation increments

1. Finish Stage 0 and get the hermetic default suite green.
2. Add the core run/event/artifact/handoff/approval contracts under
   `easy_agents` with compatibility adapters.
3. Turn the current catalog contracts into a versioned Charter and persistent
   Roster with CLI validation.
4. Compile the simple conversation agent from a real Charter and Playbook.
5. Add the SQLite run/checkpoint/task service and a policy-enforced tool call.
6. Connect Feature Architect proposals to isolated Charter/Playbook scaffolding
   and evaluation, without automatic activation.

These increments unlock the architecture. Building dozens of domain agents
before them would multiply the repository's current ad hoc state, orchestration,
and safety gaps.

## Test strategy

Every Specialist or Capability must ship with:

- schema and Charter validation;
- deterministic fake-model and fake-tool unit tests;
- golden feature-routing cases;
- allowed, denied, and approval-required policy cases;
- prompt-injection and sensitive-data cases for every untrusted input;
- task timeout, retry, cancellation, restart, and idempotency tests where
  relevant;
- offline/network-boundary tests;
- scenario traces with expected decisions and artifacts;
- quality thresholds before promotion and regression checks after promotion;
- load/resource tests for long-running, parallel, or GPU work.

Domain suites add India-specific payment, identity, tax, travel, language, and
emergency cases; Science Lab adds citation, leakage, statistics, reproducibility,
and benchmark cases; Venture Studio adds tenant/data separation, outbound
communication, deployment, legal, hiring, and spend controls.

## Definition of done

The Personal Constellation is useful—not merely large—when:

- the user can submit one feature or mission in plain language;
- the system explains whether it will reuse, compose, extend, or create;
- new work produces typed, testable, least-privilege Charters and Playbooks;
- only evaluated and approved versions become active;
- Specialists may overlap across Guilds without gaining implicit authority;
- all work is durable, cancellable, budgeted, observable, and recoverable;
- strict offline operation is enforced for local profiles;
- memory and data are scoped, attributable, editable, exportable, and
  forgettable;
- high-risk decisions and external actions remain under human control;
- home, research, and startup missions can be composed from the same shared
  platform contracts;
- adding the hundredth registered Specialist is a catalog and evaluation change,
  not a framework rewrite.
