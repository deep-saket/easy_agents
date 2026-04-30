# Offline Fixture Data

These JSON files back the local Connections Agent tools.

- `cases.json`: delinquency case records
- `customers.json`: customer verification challenge data
- `policies.json`: loan policy constraints

Runtime-generated files are written under `../runtime/`.

## Example CLI

From repo root:

```bash
python -m agents.connections_agent.main "case_fetch case_id=COLL-1001"
python -m agents.connections_agent.main "case_prioritize portfolio_id=PORT-RETAIL-A top_k=3"
python -m agents.connections_agent.main "customer_verify case_id=COLL-1001"
python -m agents.connections_agent.main --interactive
```
