# Galaxy Knowledge Graph

Status: implemented topology, live monitoring, and replay UI

The Galaxy Map visualizes active and planned Rocky Planets together with
the reusable components that connect them. It is a topology and architecture
view: Circles, capabilities, tools, memory scopes, Playbooks, policies, models,
and platform services are all first-class nodes.

The same Control Room now overlays realtime execution. The topology continues
to describe what exists; Live and Replay show what the fleet is doing.

The canonical vocabulary is defined in
[Galaxy Terminology](../architecture/galaxy-terminology.md).

## Talk to the Galaxy

The **Wormhole** is the single logical entry point. Enter a Mission in the
panel above the graph and select **Route**. The local router
returns and highlights an explainable path:

```text
Wormhole → Personal Agent Galaxy → Circle → Planet
```

For example, “calculate a satellite RF link budget” routes through the
Satellite Communications Circle to the RF & Link-Budget Rocky Planet. Routing is
deterministic and does not invoke a model. Select **Inspect** on the result to
open that Planet and optionally run the bounded Mission with the selected
model profile.

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
| Galaxy | The top-level owned system entered through the Wormhole |
| Rogue Star | A shared external resource owned by no Galaxy and accessible to multiple Galaxies through governed Orbits; Mac Gemma is the current example |
| Constellation | A connected subgraph overlay drawn from selected parts of one or more Circles; it is not a routing layer |
| Circle | A Galaxy-level responsibility or domain group containing Planets and Components |
| Rocky Planet | A narrow specialist agent: an active Roster entry or planned Charter from the deep-tech implementation plan |
| Giant Planet | A broad non-specialist agent that coordinates varied work and delegates narrow expertise |
| Capability | A declared operation available to one or more Specialists |
| Tool | A concrete reusable implementation such as memory search or email draft |
| Memory | A data scope or storage boundary |
| Playbook | A reusable workflow or graph template |
| Policy | A central rule or approval boundary |
| Model | A configured inference dependency |
| Service | Shared platform infrastructure rather than a conversational agent |

**Circle Member** is the umbrella term for anything assigned to a Circle. A
**Planet** is an agent member: either a **Rocky Planet** with a narrow
specialist Charter or a **Giant Planet** with a broad non-specialist Charter. A
non-agent member is a **Component**, such as a capability, tool, memory Vault,
Playbook, policy, model, or service. The current executable graph contains
Rocky Planet nodes; Giant Planets are defined for the forthcoming manifest
migration.

A **Rogue Star** is outside the Circle Member taxonomy because it is outside
every Galaxy. Access does not imply ownership. The graph marks Mac Gemma as a
Rogue Star while retaining `model:mac_gemma` as its stable technical identifier
and `model` as its underlying resource kind.

Edges are typed relationships such as `routes to Circle`, `dispatches to`,
`member of`, `can use`, `uses template`, `implements`, `reads`, `writes`,
`governs`, and `guards`. Circle-to-Specialist dispatch edges are shown when an
entry route is active so the normal overview remains readable.

## Interact with it

- Open the **Guide** tab for the canonical hierarchy, terminology cards, and
  the Circle-versus-Constellation, Rocky-versus-Giant,
  Planet-versus-Component, and Galaxy-versus-Rogue-Star distinctions. It
  also includes nested-boundary and Solar System illustrations, a concrete
  grocery Mission walkthrough, term-selection examples, and the complete
  Mission-to-Mission-Log lifecycle.
- Search by name, identifier, description, or tag.
- Switch between Overview, Agents, Components, and Full presets.
- Filter to a Circle such as Employment Boundary, Energy, Satellite
  Communications, or Medical Deep-Tech.
- Toggle individual node types and lifecycle groups.
- Select a node to inspect metadata and every direct relationship.
- Select a relationship in the inspector to navigate to the other node.
- Select a Rocky Planet, enter a Sandbox mission, and build its policy-aware plan.
- Focus on one node's immediate neighborhood.
- Drag a node to pin it; release it from the inspector.
- Pan the canvas, scroll to zoom, or use Fit View.
- Turn relationship labels on when inspecting a smaller subgraph.

## Monitor and replay Missions

Use the mode switch in the top bar:

- **Map** keeps the original topology and catalog counters.
- **Live** loads a durable operations snapshot, then follows the local SSE
  stream. Specialist, Playbook, policy, model, tool, and memory nodes show
  runtime state. Bright directional edges represent actual recent activity.
- **Replay** disconnects live-follow and reconstructs the same runtime overlay
  from ordered events. Drag the timeline scrubber or choose a Mission in the
  right panel.

The Live view shows active Mission, running Specialist, and attention counts.
Runtime status and attention filters are available on the left. Selecting any
catalog node adds its retained activity to the inspector.

Waiting approval, blocked, failed, running, and completed states use text and
shape treatments as well as color. Enable **Reduce motion** to stop pulsing
rings and moving activity strokes.

The browser reconnects from its last durable event sequence. A connection loss
marks the view stale without clearing the last known graph state.

The interface uses no CDN or external JavaScript dependency. It reads the local
knowledge-graph and operations APIs, subscribes to `/api/events/stream`, and
submits sandbox tasks only to the local `/api/missions/run` endpoint.

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

Route a natural-language Mission through the same entry point:

```bash
curl -s http://127.0.0.1:8030/api/wormhole/route \
  -H 'Content-Type: application/json' \
  -d '{"objective":"plan groceries and pantry restocking"}'
```

The route response includes `wormhole_id`, `galaxy_id`, ranked `circles`, Rocky
Planet `candidates` (technical Specialist records), and concrete `paths`. Constellations remain visible in
the topology but are intentionally absent from the routing response.
`/api/missions/route` and the legacy `/api/entrypoint/route` remain compatible
aliases for the same contract.

The response contains:

```text
version
nodes[]: id, kind, label, description, status, group, tags, risk, metadata
edges[]: id, source, target, kind, label, directed, metadata
counts: node totals by kind
```

Because the UI consumes this generic contract, future domain packs can add
nodes and relationships without adding new visualization code.

The monitoring endpoints and privacy boundary are documented in
[Realtime Monitoring and Tracing](../reference/functionalities/observability.md).
