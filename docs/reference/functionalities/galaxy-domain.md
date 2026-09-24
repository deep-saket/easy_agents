# Canonical Galaxy Domain

Status: verified foundation

## What is implemented

`easy_agents.galaxy` is the terminology-first composition layer for reusable
agent systems. It provides immutable contracts for Galaxies, Circles, Rocky
and Giant Planets, non-agent Components, callable Satellites, connected
Constellations, computed Solar Systems, external Rogue Stars, Missions,
permission grants, routing, and execution results.

The implementation includes:

- whole-graph validation through `GalaxyRegistry`;
- a fluent `GalaxyBuilder` that derives symmetric Circle membership;
- exact `Wormhole → Galaxy → Circle → Planet` routing;
- one `PlanetRunner` contract for both Planet subclasses;
- a `SatelliteExecutor` policy wrapper over the existing `ToolExecutor`;
- deterministic YAML schema version 2 load, dump, and save helpers;
- a read-only adapter for all 70 current version-1 specialist roles;
- canonical topology projection with duplicate and dangling-edge validation;
- additive local version-2 HTTP APIs and the `easy-agents-galaxy` CLI; and
- a public terminology matrix plus an accepted vocabulary ADR.

## Safety boundaries

Configuration models reject unknown fields and are frozen after validation.
The registry rejects missing ownership, invalid Planet subclasses, asymmetric
membership, unknown Charter dependencies, invalid delegation targets, and
Constellation entities outside the declared Circles. Permission Grants support
intersection but not widening. Rogue Star access checks effects, exact hosts,
network mode, and approval state.

Satellite authorization checks the calling Planet's Charter, Work Order grant,
declared effects, approval, network policy, and payload size before delegating
to the technical executor. Registering a Component, Satellite, handler, or
Rogue Star never grants authority on its own.

## Current limits

`GalaxyRuntime` is a small synchronous composition runtime. It does not yet
provide durable cancellation, wall-clock enforcement, token/Satellite counters,
retry scheduling, recursive delegation orchestration, authentication, or
cross-process isolation. `MissionBudget` models those ceilings, but only the
maximum Planet count is enforced by this runtime today.

The existing Control Room, event stream, and legacy applications continue to
use compatibility projections while their migration proceeds. Local HTTP
services must remain loopback-only until principal authentication, Galaxy
authorization, rate limits, and concurrency limits are implemented.

## Verification

Run the canonical foundation tests:

```bash
PYTHONPATH=src python -m pytest -q tests/test_galaxy_domain.py
```

The 18-test suite covers both Planet classes, builder behavior, permission narrowing,
Satellite policy, Rogue Star allowlists, Constellation connectivity, YAML
round-trips, strict schemas, the all-70-role adapter, topology validation,
Wormhole routing, v2 APIs, CLI behavior, terminology contracts, docstrings,
and module headers.

For construction examples, see [Build Your Own Galaxy](../../guides/build-your-galaxy.md).
For every public class, see [Galaxy Domain API](../galaxy-domain-api.md).
For remaining migration and hardening work, see the
[Terminology-First Domain Model Migration](../../plans/terminology-domain-model-migration.md).
