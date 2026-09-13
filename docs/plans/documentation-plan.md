# Documentation Plan

## Assessment

The repository documentation was partially good, but not sufficient for onboarding or agent creation.

Its strongest areas were the framework architecture notes, memory design, MailMind scope documents, and the detailed Collection Agent README. The main problems were discoverability and the absence of a verified path from clone to working agent. Readers also could not reliably tell which ideas were implemented and which belonged to the future roadmap.

| Area | Assessment before this plan | Main gap |
| --- | --- | --- |
| Documentation index | Present but file-oriented | No audience or task-based navigation |
| Setup | Scattered across the root and agent READMEs | No provider-free first run |
| Functionality reference | Architecture pages described components | No honest capability/maturity matrix |
| Agent authoring | No end-to-end guide | No current code-first example or completion checklist |
| Existing agents | Uneven | Collection is detailed; some agents are placeholders; status was not obvious |
| Operations | Agent-specific fragments | No common deployment, security, backup, or troubleshooting guide |
| API/reference | Mostly docstrings and source | No generated or curated public API reference |
| Current vs future | Roadmaps existed beside runtime docs | Planned CLI and manifests could be mistaken for working features |
| Test guidance | `pytest` was mentioned | No distinction between offline unit tests and live integration/provider tests |

## Documentation Goals

The documentation should let a reader answer five questions without reading the whole source tree:

1. What works now?
2. What can run fully offline?
3. How do I get one successful run?
4. How do I create, test, and compose an agent?
5. What is planned but not implemented?

## Audience Paths

### First-time user

Start at the documentation index, install the core project, complete a credential-free smoke test, and choose an existing agent.

### Agent author

Read the current capability boundary, build a deterministic tool-using agent, add memory or a model intentionally, test it, and add agent-specific usage documentation.

### Framework contributor

Read the framework and memory architecture, inspect public contracts, run isolated tests, then consult the roadmap for the intended target architecture.

### Operator

Find configuration, secrets, local/hosted dependency boundaries, traces, runtime storage, health checks, backups, and failure recovery in one operations section.

## Target Information Architecture

```text
docs/
  README.md                         # task-based entry point
  getting-started.md                # install and first offline run
  guides/
    create-an-agent.md              # current authoring workflow
    feature-intake.md               # current feature-fit workflow and safety boundary
    compose-agents.md               # future focused guide
    configure-models.md             # future provider/offline guide
    use-memory.md                   # future task-oriented memory guide
  reference/
    current-capabilities.md         # implemented vs limited vs planned
    configuration.md                # future settings and precedence reference
    public-api.md                   # future stable contracts
  architecture/
    framework-overview.md
    memory-architecture.md
    conversation-management.md
  agents/
    ...                             # one overview/usage set per real agent
  operations/
    security.md                     # future secrets, PII, permissions
    observability.md                # future logs/traces/run debugging
    troubleshooting.md              # future known failures and remedies
  conventions/
    docstring-rules.md
    documentation-rules.md          # future page standards
  plans/
    documentation-plan.md
    offline-agent-platform-roadmap.md
    personal-constellation-plan.md
  vision/
    personal-agent-constellation.md
```

## Delivery Plan

### P0: Make the repository usable from documentation

Status: completed in the initial documentation pass.

- Add a task-based documentation index.
- Add a provider-free installation and smoke-test guide.
- Add a current capability and limitation reference.
- Add a complete, tested, code-first agent-authoring guide.
- Mark placeholder agents and future manifest/CLI concepts clearly.
- Link the root README to the primary user journeys.

### P1: Cover common author workflows

Status: in progress.

- Completed: add a model-provider reference with local and OpenAI-compatible paths.
- Completed: add a memory recipe covering working, persistent, and hybrid retrieval.
- Completed: document current agent composition, child sessions, and limits.
- Completed: add a configuration reference checked against `AppSettings`.
- Completed: add current usage and verification notes for MailMind and both collection specialist agents.
- Remaining: expand agent composition into a dedicated error propagation and timeout guide after those contracts are centralized.
- Add architecture decision records for package namespace, run contract, state layering, and capability policy.

### P2: Make operation safe and repeatable

Status: planned.

- Separate and mark unit, integration, provider, and end-to-end tests.
- Document secrets, PII, retention, approvals, and tool permission boundaries.
- Document runtime directories, backups, migration, cleanup, and recovery.
- Document trace fields and a step-by-step failed-run investigation.
- Add deployment recipes only after the runtime and configuration contracts stabilize.

### P3: Keep documentation correct automatically

Status: planned.

- Add a Markdown link checker in CI.
- Execute quickstart snippets or mirror them in tests.
- Verify every documented CLI with `--help` in CI.
- Generate settings and tool catalogs from source where practical.
- Add a docs-change checklist to pull requests that modify public behavior.

## Page Standard

Every runnable agent README should contain:

- status: working, experimental, or placeholder
- purpose and non-goals
- prerequisites and optional dependencies
- configuration with secret names but no secret values
- one minimal runnable command
- expected output or health check
- graph or lifecycle explanation
- tools and side effects
- memory and storage paths
- trace and debugging instructions
- test command
- known limitations

Every command must state the working directory and whether it requires network access, credentials, a local model server, or optional packages.

## Definition of Done for Documentation

A documentation change is complete when:

- links resolve from the file in which they appear
- commands have been executed in a clean or representative environment
- output examples match current behavior
- current and planned features are visibly separated
- credentials and personal filesystem paths are absent
- destructive or side-effecting actions are labeled
- a new user can identify the next page without searching the repository
- related code changes update the relevant capability or usage page

## Maintenance Ownership

Documentation should be updated in the same change as the behavior it describes. The code owner for a framework area owns its reference page; the owner of a concrete agent owns that agent's README and usage guide. Quarterly audits should check links, setup commands, provider names, optional extras, screenshots, and the implemented/planned boundary.

The roadmap is not a substitute for current documentation. When a roadmap feature ships, move its user-facing behavior into a guide or reference page and update the capability matrix.
