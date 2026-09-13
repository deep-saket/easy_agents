# Graph Builder

Status: verified as a local design, validation, and scaffold-export tool.

## Start the UI

Run from the repository root with `.venv` installed:

```bash
./run/graph_builder.sh
```

Open `http://127.0.0.1:8020`. Health endpoint:

```bash
curl http://127.0.0.1:8020/health
```

Expected output:

```json
{"status":"ok"}
```

The launcher sources `setup.sh`, sets the host/port from `GRAPH_BUILDER_HOST` and `GRAPH_BUILDER_PORT`, and starts Uvicorn with reload enabled.

## Graph Specification

The current JSON format is graph spec v2. It contains:

- graph metadata: name and mode
- nodes: ID, label, kind, module, description, allowed tools, config, and position
- edges: ID, source/target nodes and ports, plus metadata

Supported modes:

- `chain_of_thought`: exactly one root and leaf, no branching or cycles
- `tree_of_thought`: tree-oriented structural rules
- `graph_of_thought`: general graph mode, including cycles

Supported node kinds include thought, decision, tool, agent, memory, reflect, respond, router, and custom.

## API

| Endpoint | Function |
| --- | --- |
| `GET /health` | Process health |
| `GET /api/catalog` | Shared node catalog, known nested agents, graph modes, and config metadata |
| `POST /api/validate` | Normalize and validate a graph payload |
| `POST /api/export/json` | Return normalized graph spec and issues |
| `POST /api/export/python` | Return a Python scaffold |

POST bodies use this wrapper:

```json
{
  "payload": {
    "version": 2,
    "graph": {"name": "Example", "mode": "graph_of_thought"},
    "nodes": [],
    "edges": []
  }
}
```

## Verification

Five API tests passed. They cover catalog metadata, chain branching validation, graph-mode cycles, v1-to-v2 migration, JSON export, and Python scaffold contents. A separate `/health` request returned HTTP 200 and `{"status":"ok"}`.

## Important Export Limitation

The Python export contains `PlaceholderNode` objects and TODO comments. It does not instantiate the chosen concrete node classes, inject tools/models/storage, enforce displayed retry/timeout/approval metadata, or create a production entrypoint.

Treat the output as an editable reference scaffold, not generated runnable agent code.
