# Constellation Feature Intake

Implementation:

- `src/easy_agents/constellation/models.py`
- `src/easy_agents/constellation/directory.py`
- `src/easy_agents/constellation/feature_intake.py`
- `src/easy_agents/constellation/cli.py`
- `src/easy_agents/constellation/api.py`
- `src/easy_agents/constellation/default_catalog.yaml`

Tests: `tests/test_constellation_feature_intake.py`

## Implemented functionality

| Functionality | Status | Verification |
| --- | --- | --- |
| Load the packaged Roster | Implemented | catalog fixture loads and indexes all entries |
| Load a custom YAML Roster | Implemented | typed validation through `ConstellationCatalog` |
| Reject dangling Guild/Capability references | Implemented | negative contract test |
| Represent multi-Guild Liaisons | Implemented | Steward and Safety Steward membership test |
| Reuse an existing Capability | Implemented | research-summary test |
| Compose a Playbook recommendation | Implemented as proposal | household tracking plus reminder test |
| Extend an existing Specialist | Implemented as proposal | missing payment-effect test |
| Generate a new Draft Charter | Implemented as proposal | unfamiliar hydroponics-domain test |
| Infer effects and policy risk | Implemented baseline | payment, outbound communication, and sensitive identity tests |
| Produce stable proposal IDs | Implemented | deterministic repeated-request test |
| Expose local health, Roster, and assessment API | Implemented | FastAPI contract tests |
| Scaffold runnable agent code | Not implemented | planned |
| Persist/install/activate a Charter | Not implemented | planned |
| Execute a proposed Playbook | Not implemented | planned |
| Feature-intake UI | Not implemented | planned for Control Room |

Run the focused tests:

```bash
PYTHONPATH=src pytest -q tests/test_constellation_feature_intake.py
```

Run the CLI:

```bash
PYTHONPATH=src python -m easy_agents.constellation.cli \
  "Send an investor update email"
```

Run the loopback-only development API:

```bash
PYTHONPATH=src uvicorn easy_agents.constellation.api:app \
  --host 127.0.0.1 --port 8030
```

See [Feature Intake and Draft Charters](../../guides/feature-intake.md) for the
full usage contract and safety boundary.
