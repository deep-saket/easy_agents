# Run the Specialist Fleet

Status: implemented safe local advisory runtime

The Personal Agent Constellation now compiles every Specialist in the current
and deep-tech rosters into a validated Charter. The same runtime serves all 70
Specialists; adding another Charter does not require another Python agent
class or background model process.

## What is available

| Component | Count | Runtime state |
| --- | ---: | --- |
| Specialist Charters | 70 | 14 active, 56 sandboxed |
| Shared Playbooks | 9 | implemented |
| Policy profiles | 4 | implemented |
| Memory scopes | 6 | defined and policy-enforced |
| Local model profile | 1 | Mac Gemma on loopback |

Sandboxed Specialists can be inspected, routed, policy-checked, and run in
advisory mode. They cannot silently send messages, call people, buy anything,
move money, publish, use employer material across scopes, diagnose, prescribe,
access the public network, or control hardware.

## List and inspect agents

Run from the repository root:

```bash
PYTHONPATH=src .venv/bin/python -m easy_agents.fleet.cli list

PYTHONPATH=src .venv/bin/python -m easy_agents.fleet.cli \
  inspect rf_link_budget_specialist
```

After installing the project in editable mode, the shorter command is also
available:

```bash
.venv/bin/pip install -e . --no-deps
.venv/bin/easy-agents list
```

## Route a mission

Routing is deterministic and does not start a model:

```bash
.venv/bin/easy-agents route \
  "calculate a satellite RF link budget"
```

Every request enters the Galaxy through the reusable **Wormhole**. It first
selects the Galaxy, then one or more Circles, and finally ranks Specialists
inside those Circles. The result contains the Wormhole, selected Galaxy,
ranked Circles, Specialist candidates,
matched terms, lifecycle state, and concrete routing paths. Only the selected
Specialists are instantiated for a Mission; registering 70 agents does not
keep 70 model loops alive.

In the canonical vocabulary, an agent is a **Planet**. Circles may contain
**Rocky Planets** (specialists) and **Giant Planets** (broad non-specialists),
plus non-agent Components. This runtime currently compiles the existing Rocky
Planet Roster through `SpecialistManifest`; Giant Planet does not yet have a
separate executable manifest type.

## Build a deterministic safe plan

Without a model, a Specialist returns the selected Playbook, memory scope,
policy outcome, and auditable step plan:

```bash
.venv/bin/easy-agents run \
  "compare two battery storage concepts" \
  --agent electrochemistry_storage_specialist
```

Ask several Specialists to work on the same Mission:

```bash
.venv/bin/easy-agents run \
  "compare battery opportunities and challenge the scientific evidence" \
  --team-size 3
```

Each child Work order carries an explicit effect set and one memory scope.
Delegation intersects permissions with the child Charter and cannot widen
authority.

## Use the local Mac Gemma model

Start the Mac model service described in
[Local Gemma Integration](./use-local-gemma.md), then run:

```bash
.venv/bin/easy-agents run \
  "review this local battery thesis and identify the cheapest falsification" \
  --agent scientific_reviewer \
  --model mac-gemma
```

The runtime supplies the model with the selected Charter, Playbook, policy
profiles, and memory-scope boundary. Model text is advisory: it cannot bypass
the policy engine or claim that an external action happened. The client calls
the separately managed Mac-serving repository over
`http://127.0.0.1:8080/v1/completions`; no model weights or serving code are
installed in this repository. In the Galaxy topology, this shared external
service is a **Rogue Star**: it belongs to no Galaxy and can be reused by
multiple Galaxies through explicit policy-controlled access.

## Gates and safety examples

A call request stops at a human Gate:

```bash
.venv/bin/easy-agents run \
  "call mom this evening" \
  --agent family_relationships_specialist
```

Passing `--approve call` records approval in the Mission request, but the
current advisory runtime still does not dial a phone. A future approved phone
connector must execute through the central capability executor.

The following are blocked by default:

- any Specialist reading a memory scope not declared by its Charter;
- exploration agents reading `employer_authorized` memory;
- non-loopback network access under `offline_strict`;
- medical diagnosis or prescription;
- undeclared, high-risk, or authority-widening effects;
- access to the dormant `future_company` scope.

## Use the Control Room

Start the graph UI:

```bash
./run/constellation.sh
```

Open `http://127.0.0.1:8030`, select a Specialist, and enter a bounded task
under **Sandbox mission**. Choose **Mac Gemma · external local service** for a
real model-backed advisory Run, or **Deterministic plan · no model** for the
policy-aware plan only. Neither choice invokes an external effect.

Alternatively, type the request into the **Wormhole** above the map.
The UI calls the local entry API and focuses the graph on the resulting
Wormhole → Galaxy → Circle → Rocky Planet Trajectory before you
inspect or run the Specialist.

To exercise the complete roster, switch to **Live** and select
**Test all 70 planets**. The Control Room creates one correlated validation
Mission, runs every compiled Specialist with the local model and network
disabled, and shows the per-agent result in realtime. The completed Mission is
retained in **Replay** for inspection.

## Validate the complete fleet

The fleet audit is deliberately safe and deterministic. For each registered
Specialist it:

- instantiates the shared runtime from the Specialist Charter;
- submits the same bounded advisory objective with read-only effects;
- forces `llm=None`, denies network access, and invokes no external connector;
- records the selected Playbook, Run ID, duration, warnings, and terminal
  outcome;
- continues after an individual failure so the report always covers the whole
  roster.

An agent passes when it reaches `planned` or `completed`. This validates roster
compilation, policy evaluation, Playbook selection, lifecycle execution,
observability persistence, and replay correlation. It does not validate the
scientific correctness of a domain answer or a real connector.

## API

The local API exposes the same contracts used by the CLI and UI:

```text
GET  /api/fleet
GET  /api/fleet/{specialist_id}
GET  /api/models/mac-gemma/status
POST /api/wormhole/route
POST /api/entrypoint/route  # compatibility alias
POST /api/missions/route
POST /api/missions/run
POST /api/fleet/test
```

Example:

```bash
curl -s http://127.0.0.1:8030/api/missions/run \
  -H 'Content-Type: application/json' \
  -d '{
    "objective": "calculate a satellite RF link budget",
    "specialist_id": "rf_link_budget_specialist",
    "model_id": "mac_gemma"
  }'
```

Run the safe whole-fleet audit:

```bash
curl -s -X POST http://127.0.0.1:8030/api/fleet/test
```

The response includes aggregate counts and one result for each registered
Specialist. All Runs share the returned `mission_id` and can be inspected in
the monitoring timeline.

## Current boundary

This release builds and runs the whole roster as policy-governed advisory
agents. It does not yet claim that every domain connector exists. The event
history and Mission projections are durable, but resumable execution
checkpoints, resumable approvals, artifact storage, evaluated domain
calculators, scheduled wakeups, and real approved call/purchase/submission
connectors remain later platform increments. Those components can be added
once and reused by every authorized Charter.

Implementation:

- `src/easy_agents/fleet/models.py`
- `src/easy_agents/fleet/gateway.py`
- `src/easy_agents/fleet/registry.py`
- `src/easy_agents/fleet/policy.py`
- `src/easy_agents/fleet/model_profiles.py`
- `src/easy_agents/fleet/runtime.py`
- `src/easy_agents/fleet/runtime_catalog.yaml`
- `src/easy_agents/fleet/cli.py`

Tests: `tests/test_fleet_runtime.py` (18 focused tests, including hierarchical
entry routing, external-model selection, empty-output failure handling, and a
correlated 70-Specialist validation Mission)
