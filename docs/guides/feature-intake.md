# Feature Intake and Draft Charters

The Feature Architect is the first implemented slice of the Personal Agent
Constellation. Give it a feature in plain language and it returns an auditable
proposal to:

- reuse an existing Capability;
- compose a multi-Specialist Playbook;
- extend the closest Specialist; or
- create a non-runnable Draft Charter for a new Specialist.

It runs locally, uses deterministic matching, and makes no model or network
calls. It does not execute the requested feature.

## Try it

From a development checkout:

```bash
PYTHONPATH=src python -m easy_agents.constellation.cli \
  "Track my household electricity bill and remind me before the due date"
```

After installing the project in editable mode:

```bash
python -m pip install -e .
constellation-intake "Summarize three machine learning research papers"
```

Add `--compact` for one-line JSON. Add `--catalog path/to/catalog.yaml` to use a
custom Roster.

The returned `FeatureProposal` includes:

- a stable `proposal_id` derived from the request;
- `decision` and confidence;
- inferred Guilds and requested effects;
- ranked Specialist and Capability matches with matched terms;
- risk and whether a human Gate is required;
- whether the matched work requires network access;
- missing Capability identifiers;
- an optional Draft Charter;
- an explanation and the required next steps.

Example summary:

```json
{
  "decision": "compose_playbook",
  "inferred_guilds": ["home", "life_admin"],
  "requested_effects": ["write"],
  "risk": "moderate",
  "network_required": false,
  "requires_human_approval": false,
  "safe_to_auto_scaffold": false
}
```

The real output also includes the matches, rationale, and next steps.

## Decision behavior

| Decision | Meaning | Current next step |
| --- | --- | --- |
| `reuse_existing` | A matching Specialist already owns compatible Capabilities | Bind and evaluate that existing path |
| `compose_playbook` | The request contains multiple strong responsibilities | Generate a typed Playbook using the matched Specialists |
| `extend_specialist` | The domain fits, but required effects are missing | Propose a Capability and Charter diff |
| `create_specialist` | No Specialist has sufficient domain overlap | Review the generated Draft Charter |

Examples from the default Roster:

| Request | Expected decision | Safety outcome |
| --- | --- | --- |
| “Summarize three machine learning research papers” | reuse Knowledge Librarian | read-only; no Gate |
| “Track my electricity bill and remind me before the due date” | compose Household Operator and Schedule Coordinator | draft/track; sandbox evaluation |
| “Pay my electricity bill” | extend because payment capability does not exist | critical risk; Gate required |
| “Manage a hydroponic farm nutrient pump” | create Draft Charter | no permissions; proposed only |
| “Send an investor update email” | reuse drafting/sending capability | outbound Gate required |
| “Create an Aadhaar renewal reminder” | reuse official-document tracking | sensitive-data Gate required |

## Python API

```python
from easy_agents.constellation import FeatureIntakeService

architect = FeatureIntakeService()
proposal = architect.assess("Compare competitors for my startup")

print(proposal.decision)
print(proposal.matched_specialists)
print(proposal.model_dump_json(indent=2))
```

Use an explicit directory to validate and assess a custom Roster:

```python
from easy_agents.constellation import ConstellationDirectory, FeatureIntakeService

directory = ConstellationDirectory.from_yaml("my-constellation.yaml")
proposal = FeatureIntakeService(directory).assess("Prepare a new weekly report")
```

## Local API

The same contracts are exposed for a future Control Room or another local
client:

```bash
PYTHONPATH=src uvicorn --factory easy_agents.constellation.api:create_app \
  --host 127.0.0.1 --port 8030
```

Endpoints:

| Method and path | Behavior |
| --- | --- |
| `GET /health` | Catalog version and Roster counts |
| `GET /api/constellation` | Validated Guild, Capability, and Specialist catalog |
| `POST /api/features/assess` | Accept a `FeatureRequest` and return a `FeatureProposal` |

Example request:

```bash
curl -X POST http://127.0.0.1:8030/api/features/assess \
  -H 'Content-Type: application/json' \
  -d '{"feature":"Pay my electricity bill"}'
```

The API binds nowhere by itself; the command above deliberately uses loopback.
It has no authentication and must not be exposed to another machine.

## Catalog format

The packaged starter catalog is
`src/easy_agents/constellation/default_catalog.yaml`. Its minimum shape is:

```yaml
version: 1
guilds:
  - id: my_guild
    display_name: My Guild
    purpose: The domain this group owns.
    tags: [domain, topic]

capabilities:
  - id: reports.summarize
    display_name: Summarize reports
    description: Read and summarize a permitted report.
    tags: [report, summarize]
    effects: [read]
    risk: low
    network_required: false
    approval_required: false

specialists:
  - id: report_specialist
    display_name: Report Specialist
    purpose: Produce sourced report summaries.
    guilds: [my_guild]
    capability_ids: [reports.summarize]
    tags: [report, summarize]
    liaison: false
    status: active
```

Identifiers must be unique. Every Specialist Guild and Capability reference
must exist, or loading fails. A Specialist may join multiple Guilds; setting
`liaison: true` records the intended UI role but grants no additional access.

Effects currently understood by risk inference include `read`, `write`,
`compute`, `send`, `payment`, `delete`, `shell`, and `device_control`.

## Creation safety

`create_specialist` does not mean “silently launch code.” It produces a
`DraftCharter` with:

- status `proposed`;
- no requested permissions;
- a mission statement;
- candidate Guilds and missing Capabilities;
- inferred risk.

The target lifecycle is:

```text
proposed -> scaffolded -> sandboxed -> evaluated -> approved -> active
                                                    -> quarantined -> retired
```

`safe_to_auto_scaffold` only means an isolated skeleton may be generated. It
never authorizes activation, credentials, network access, sensitive data, or
external side effects. Payments, deletion, device control, shell/deployment,
outbound communication, and sensitive identity/medical/legal/tax work require a
human Gate.

## Current limitations

The first slice is deliberately small:

- matching is lexical and synonym-based, not yet schema- or embedding-aware;
- proposals are not persisted;
- it does not yet generate a Charter file or Playbook;
- it does not install, evaluate, promote, quarantine, or retire Specialists;
- it does not inspect runtime health or resource availability;
- its local API is an unauthenticated development surface, not the finished
  Wormhole or Control Room;
- it cannot execute the requested feature;
- a human should review low-confidence results and all domain/risk boundaries.

The hardening and integration work is sequenced in the
[Personal Constellation Gap and Delivery Plan](../plans/personal-constellation-plan.md).
