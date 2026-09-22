# Constellation Knowledge Graph

Status: implemented local UI

The Constellation Map visualizes active and planned Specialists together with
the reusable components that connect them. It is a topology and architecture
view: Circles, capabilities, tools, memory scopes, Playbooks, policies, models,
and platform services are all first-class nodes.

## Run it

From the repository root:

```bash
./run/constellation.sh
```

Open `http://127.0.0.1:8030`.

Use another local port when needed:

```bash
CONSTELLATION_PORT=8031 ./run/constellation.sh
```

The launcher fails safely when the requested port is occupied. It does not
terminate another process.

## What the graph shows

| Node | Meaning |
| --- | --- |
| Specialist | Active Roster entry or planned Charter from the deep-tech implementation plan |
| Circle | A many-to-many responsibility or domain group |
| Capability | A declared operation available to one or more Specialists |
| Tool | A concrete reusable implementation such as memory search or email draft |
| Memory | A data scope or storage boundary |
| Playbook | A reusable workflow or graph template |
| Policy | A central rule or approval boundary |
| Model | A configured inference dependency |
| Service | Shared platform infrastructure rather than a conversational agent |

Edges are typed relationships such as `member of`, `can use`, `uses template`,
`implements`, `reads`, `writes`, `governs`, `guards`, and `routes to`.

## Interact with it

- Search by name, identifier, description, or tag.
- Switch between Overview, Agents, Components, and Full presets.
- Filter to a Circle such as Employment Boundary, Energy, Satellite
  Communications, or Medical Deep-Tech.
- Toggle individual node types and lifecycle groups.
- Select a node to inspect metadata and every direct relationship.
- Select a relationship in the inspector to navigate to the other node.
- Focus on one node's immediate neighborhood.
- Drag a node to pin it; release it from the inspector.
- Pan the canvas, scroll to zoom, or use Fit View.
- Turn relationship labels on when inspecting a smaller subgraph.

The interface uses no CDN or external JavaScript dependency and calls only the
local `/api/knowledge-graph` endpoint.

## Data sources

The API combines two validated sources:

1. [`default_catalog.yaml`](../../src/easy_agents/constellation/default_catalog.yaml)
   supplies the current Roster, Circles, capabilities, lifecycle status, and
   ownership edges.
2. [`knowledge_graph.yaml`](../../src/easy_agents/constellation/knowledge_graph.yaml)
   supplies planned deep-tech roles and reusable memory, tool, Playbook,
   policy, model, and service nodes.

The typed projection lives in
[`knowledge_graph.py`](../../src/easy_agents/constellation/knowledge_graph.py).
It rejects duplicate identifiers and relationships whose endpoints do not
exist.

## Memory boundary

Memory nodes currently represent namespaces and architectural storage
boundaries. The UI deliberately does not expose the contents of personal,
employer-authorized, exploration, or future-company memories.

A future Memory Vault may show individual records only through scoped APIs with
provenance, sensitivity, retention, editing, export, and deletion controls.
Do not put secrets or sensitive memory text in `knowledge_graph.yaml`.

## API

The graph is available independently of the UI:

```bash
curl http://127.0.0.1:8030/api/knowledge-graph
```

The response contains:

```text
version
nodes[]: id, kind, label, description, status, group, tags, risk, metadata
edges[]: id, source, target, kind, label, directed, metadata
counts: node totals by kind
```

Because the UI consumes this generic contract, future domain packs can add
nodes and relationships without adding new visualization code.
