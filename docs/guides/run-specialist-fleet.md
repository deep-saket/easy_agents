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

The result contains ranked Specialists, matched terms, lifecycle state, and
Guild membership. Only the selected Specialists are instantiated for a
Mission; registering 70 agents does not keep 70 model loops alive.

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
the policy engine or claim that an external action happened.

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

Open `http://127.0.0.1:8030`, select a Specialist, enter a bounded task under
**Sandbox mission**, and select **Build safe plan**. The inspector displays the
policy-aware result without invoking an external action.

## API

The local API exposes the same contracts used by the CLI and UI:

```text
GET  /api/fleet
GET  /api/fleet/{specialist_id}
POST /api/missions/route
POST /api/missions/run
```

Example:

```bash
curl -s http://127.0.0.1:8030/api/missions/run \
  -H 'Content-Type: application/json' \
  -d '{
    "objective": "calculate a satellite RF link budget",
    "specialist_id": "rf_link_budget_specialist"
  }'
```

## Current boundary

This release builds and runs the whole roster as policy-governed advisory
agents. It does not yet claim that every domain connector exists. Durable
Mission persistence, resumable approvals, artifact storage, evaluated domain
calculators, scheduled wakeups, and real approved call/purchase/submission
connectors remain later platform increments. Those components can be added
once and reused by every authorized Charter.

Implementation:

- `src/easy_agents/fleet/models.py`
- `src/easy_agents/fleet/registry.py`
- `src/easy_agents/fleet/policy.py`
- `src/easy_agents/fleet/runtime.py`
- `src/easy_agents/fleet/runtime_catalog.yaml`
- `src/easy_agents/fleet/cli.py`

Tests: `tests/test_fleet_runtime.py`
