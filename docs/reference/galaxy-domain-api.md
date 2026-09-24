# Galaxy Domain API

Status: implemented in `easy_agents.galaxy`

This reference lists the supported public contracts. All configuration models
are Pydantic models with `extra="forbid"`; most are frozen after validation.

## Structure

| Class | Responsibility | Important boundary |
| --- | --- | --- |
| `Galaxy` | Owns Circle identifiers and Access Orbits | Never owns a Rogue Star |
| `Circle` | Groups Planet and Component references | Does not execute work |
| `CircleMember` | Common identity and Circle membership | Base of Planet and Component |
| `Planet` | Common agent identity and Charter | Instantiate Rocky or Giant subclasses |
| `RockyPlanet` | Narrow specialist agent | Must declare expertise and boundary |
| `GiantPlanet` | Broad coordinating agent | Delegation uses an allowlist and depth cap |
| `Component` | Non-agent enabling or constraining resource | Cannot own Missions or Work Orders |
| `Satellite` | Callable tool-backed Component | Execution stays in `ToolExecutor` |
| `RogueStar` | External shared model/service/API/data resource | Exists outside every Galaxy |
| `AccessOrbit` | One Galaxy's bounded Rogue Star access | Exact host/effect allowlist |
| `Constellation` | Connected graph overlay over Circle parts | Not an ownership or routing layer |
| `Orbit` | Typed directed graph relationship | Endpoints must exist in the overlay |
| `SolarSystem` | Computed one-Planet neighborhood | Not a worker or persisted owner |

## Work and execution

| Class | Responsibility |
| --- | --- |
| `Mission` | User goal and requested—not granted—authority |
| `MissionBudget` | Timeout, team, Satellite, token, and delegation bounds |
| `Trajectory` | Explainable Wormhole → Galaxy → Circle → Planet route |
| `Crew` | Temporary multi-Planet Mission team |
| `PermissionGrant` | Authority that supports intersection but not widening |
| `WorkOrder` | Bounded delegation to one Planet |
| `FlightPlan` | Ordered Playbook step identifiers |
| `PlanetRunResult` | Auditable result from one Planet |
| `GalaxyMissionResult` | Aggregate Mission result and synthesis |
| `Wormhole` | Deterministic model-free router |
| `PlanetRunner` | Validates a Work Order and calls one registered handler |
| `GalaxyRuntime` | Composes Wormhole routing and Planet execution |
| `SatelliteCall` | One bounded Planet-to-Satellite invocation request |
| `SatelliteExecutor` | Authorizes Satellite calls before `ToolExecutor` |

`GalaxyRuntime` is deliberately synchronous and minimal. It enforces Charter
scope and the Mission's maximum Planet count, but it does not yet enforce
wall-clock timeouts, token/call counters, cancellation, retry scheduling, or
durable recursive delegation. `MissionBudget` carries those limits so a durable
runtime can implement them without changing the Mission schema.

## Policy, state, and operations

| Class | Responsibility |
| --- | --- |
| `Charter` | Planet purpose, dependencies, effects, and prohibited actions |
| `Gate` | Deterministic policy or approval boundary |
| `Vault` | Scoped memory/data-isolation Component |
| `Observatory` | Galaxy monitoring and replay configuration |
| `MissionLog` | Ordered redacted Mission events |
| `MissionLogEntry` | Correlated and causally linked event record |

## Composition and persistence

| API | Responsibility |
| --- | --- |
| `GalaxyRegistry` | Validates and indexes the complete object graph |
| `GalaxyBuilder` | Derives symmetric Circle membership before registry validation |
| `GalaxySnapshotV2` | Versioned portable serialization contract |
| `load_galaxy()` | Loads and validates version-2 YAML |
| `dump_galaxy()` | Serializes deterministic version-2 YAML |
| `save_galaxy()` | Writes an exact caller-selected YAML file |
| `build_topology()` | Projects canonical topology kinds and Orbits |
| `registry_from_fleet()` | Read-only v1 FleetRegistry compatibility adapter |

The `easy-agents-galaxy` CLI validates catalogs, prints normalized snapshots,
and routes Missions without executing effects.

## Stable compatibility policy

- New code uses canonical class and field names.
- Existing `guild:*`, `specialist:*`, `tool:*`, and `tool.*` identifiers remain
  valid compatibility identifiers.
- Version-1 API, YAML, and event contracts are not silently rewritten.
- Version-2 snapshots use an explicit `version: 2` discriminator.
- Display labels may change; persisted identifiers require a migration.

See [Build Your Own Galaxy](../guides/build-your-galaxy.md) for complete
construction and execution examples.
