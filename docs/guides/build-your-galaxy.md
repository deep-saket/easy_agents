# Build Your Own Galaxy

Status: implemented canonical domain API

This guide shows how to create a complete agent system with the public
`easy_agents.galaxy` package. The package is infrastructure-neutral: you define
validated domain objects first, then attach your own Python, graph, local-model,
or service handlers through `PlanetRunner`.

## The construction order

Build from the smallest reusable contracts outward:

```text
Components and Satellites
        ↓
      Charter
        ↓
Rocky or Giant Planet
        ↓
       Circle
        ↓
       Galaxy ── governed access ──→ Rogue Star
        ↓
    Constellation (optional connected overlay)
        ↓
   GalaxyRegistry → Wormhole → GalaxyRuntime
```

The registry validates the whole object graph. It rejects missing Charter
dependencies, mismatched Circle membership, dangling Constellation nodes,
duplicate identifiers, invalid Rogue Star access, and unknown configuration
fields before execution begins.

## 1. Import the public API

```python
from easy_agents.galaxy import (
    AccessOrbit,
    Charter,
    Circle,
    Component,
    ComponentKind,
    EntityKind,
    EntityRef,
    Galaxy,
    GalaxyRegistry,
    GalaxyRuntime,
    Gate,
    LifecycleStatus,
    Mission,
    PlanetRunner,
    ResourceKind,
    RockyPlanet,
    RogueStar,
    Satellite,
    Vault,
)
```

Only import from `easy_agents.galaxy` in new application code. Its `__all__`
defines the supported public surface. Modules under `easy_agents.fleet` and
`easy_agents.constellation` remain compatibility implementations for existing
version-1 applications.

## 2. Create reusable Components

A Component is a non-agent Circle Member. It enables or constrains work but
cannot receive a Work Order or own a Mission.

```python
capability = Component(
    id="plan_shopping",
    display_name="Plan Shopping",
    description="Build a bounded grocery and pantry plan.",
    circle_ids=("home",),
    status=LifecycleStatus.ACTIVE,
    component_kind=ComponentKind.CAPABILITY,
    capability_ids=("plan_shopping",),
)

vault = Vault(
    id="home_vault",
    display_name="Home Vault",
    description="Private household preferences and inventory.",
    circle_ids=("home",),
    status=LifecycleStatus.ACTIVE,
    sensitivity="private",
    retention="user-controlled",
)

gate = Gate(
    id="purchase_gate",
    display_name="Purchase Gate",
    description="Requires approval before money leaves the account.",
    circle_ids=("home",),
    status=LifecycleStatus.ACTIVE,
    allowed_effects=("read", "draft"),
    approval_effects=("purchase",),
    external_network="approval",
)

shopping_playbook = Component(
    id="shopping_plan",
    display_name="Shopping Plan",
    description="Orders the safe inventory and drafting steps.",
    circle_ids=("home",),
    status=LifecycleStatus.ACTIVE,
    component_kind=ComponentKind.PLAYBOOK,
)
```

The tuple fields are deliberate. Domain objects are immutable after validation,
which prevents runtime code from silently widening a Charter or moving a member
between Circles.

## 3. Create a Satellite

A Satellite is the canonical name for a callable tool Component.

```python
inventory = Satellite(
    id="inventory_lookup",
    display_name="Inventory Lookup",
    description="Reads the current pantry inventory.",
    circle_ids=("home",),
    status=LifecycleStatus.ACTIVE,
    tool_id="inventory_lookup",  # existing ToolRegistry name
    effects=("read",),
    input_schema_name="InventoryQuery",
    output_schema_name="InventoryResult",
    network_required=False,
    approval_required=False,
    idempotent=True,
    timeout_seconds=10,
    max_attempts=2,
)
```

The Satellite stores policy and operability metadata. It does not replace
`BaseTool`, `ToolRegistry`, or `ToolExecutor`; those existing classes still
perform schema validation, execution, logging, and optional memory capture.

An existing tool can be described automatically:

```python
satellite = Satellite.from_tool(
    registered_tool,
    circle_ids=("home",),
    effects=("read",),
    timeout_seconds=10,
)
```

Non-idempotent Satellites cannot configure automatic retries. Network access
and approval requirements are explicit fields rather than planner guesses.

## 4. Write a Charter

A Charter declares a Planet's purpose and maximum dependencies. Actual Mission
authority is always the intersection of the Charter, Mission request, policy
Gates, and parent Permission Grant.

```python
charter = Charter(
    purpose="Plan household shopping without placing an order.",
    capability_ids=("plan_shopping",),
    satellite_ids=("inventory_lookup",),
    vault_ids=("home_vault",),
    playbook_ids=("shopping_plan",),
    gate_ids=("purchase_gate",),
    model_ids=("local_model",),
    allowed_effects=("read", "draft"),
    network_access="deny",
    prohibited_actions=("purchase without approval",),
)
```

Every referenced identifier must exist when the GalaxyRegistry is constructed.
A missing Satellite, Vault, Playbook, Gate, capability, model, or Rogue Star is
a validation error—not a runtime warning.

## 5. Create a Planet

Use a Rocky Planet for bounded specialist work:

```python
pantry_planner = RockyPlanet(
    id="pantry_planner",
    display_name="Pantry Planner",
    description="Specialist for groceries and pantry planning.",
    circle_ids=("home",),
    status=LifecycleStatus.ACTIVE,
    tags=("groceries", "pantry"),
    charter=charter,
    expertise=("grocery planning", "inventory"),
    specialization_boundary="Plans lists but never purchases products.",
)
```

Use a Giant Planet when the role coordinates varied work and delegates narrow
tasks:

```python
from easy_agents.galaxy import GiantPlanet

household_coordinator = GiantPlanet(
    id="household_coordinator",
    display_name="Household Coordinator",
    description="Coordinates broad household requests.",
    circle_ids=("home",),
    status=LifecycleStatus.ACTIVE,
    charter=charter,
    coordination_domains=("home", "life admin"),
    delegation_targets=("pantry_planner",),
    max_delegation_depth=1,
)
```

Both subclasses run through the same `PlanetRunner`. Inheritance represents
stable identity and validation; it does not create two separate agent
frameworks. A Giant Planet cannot delegate to itself or to an unknown Planet.

## 6. Create a Circle

Circle membership is declared on both sides so the registry can catch mistakes:

```python
home = Circle(
    id="home",
    display_name="Home",
    purpose="Coordinates household responsibilities.",
    members=(
        EntityRef(kind=EntityKind.PLANET, id="pantry_planner"),
        EntityRef(kind=EntityKind.PLANET, id="household_coordinator"),
        EntityRef(kind=EntityKind.COMPONENT, id="plan_shopping"),
        EntityRef(kind=EntityKind.SATELLITE, id="inventory_lookup"),
        EntityRef(kind=EntityKind.COMPONENT, id="home_vault"),
        EntityRef(kind=EntityKind.COMPONENT, id="shopping_plan"),
        EntityRef(kind=EntityKind.COMPONENT, id="purchase_gate"),
    ),
)
```

If a Planet declares `circle_ids=("home",)` but the Home Circle does not
reference it—or the reverse—the registry rejects the configuration.

## 7. Add a Rogue Star and its Access Orbit

A Rogue Star is outside every Galaxy:

```python
local_model = RogueStar(
    id="local_model",
    display_name="Local Model",
    description="Shared loopback inference service.",
    resource_kind=ResourceKind.MODEL,
    endpoint="http://127.0.0.1:8080/v1/completions",
    model_name="example-model",
)

model_access = AccessOrbit(
    galaxy_id="personal",
    rogue_star_id="local_model",
    allowed_effects=("inference",),
    allowed_hosts=("127.0.0.1",),
    allow_network=False,  # loopback only
)
```

`AccessOrbit.allows()` validates the effect, scheme, exact host allowlist,
network policy, and approval requirement. Registration never converts the Rogue
Star into an owned Component.

## 8. Create the Galaxy

```python
personal = Galaxy(
    id="personal",
    display_name="Personal Galaxy",
    description="My private personal-assistant system.",
    circle_ids=("home",),
    external_access=(model_access,),
    default=True,
)
```

A Circle has one owning Galaxy. Several Galaxies may have independent Access
Orbits to the same Rogue Star.

## 9. Add an optional Constellation

A Constellation is a connected graph overlay, not a routing hop:

```python
from easy_agents.galaxy import Constellation, Orbit, OrbitKind

planet_ref = EntityRef(kind=EntityKind.PLANET, id="pantry_planner")
satellite_ref = EntityRef(kind=EntityKind.SATELLITE, id="inventory_lookup")

shopping = Constellation(
    id="shopping",
    display_name="Shopping Constellation",
    circle_ids=("home",),
    nodes=(planet_ref, satellite_ref),
    orbits=(
        Orbit(
            id="pantry-inventory",
            source=planet_ref,
            target=satellite_ref,
            kind=OrbitKind.CAN_USE,
            label="can use",
        ),
    ),
)
```

Disconnected nodes, dangling endpoints, duplicate Orbits, and self-loops are
rejected.

## 10. Validate the complete registry

```python
registry = GalaxyRegistry(
    galaxies=(personal,),
    circles=(home,),
    planets=(pantry_planner, household_coordinator),
    components=(capability, vault, gate, shopping_playbook),
    satellites=(inventory,),
    rogue_stars=(local_model,),
    constellations=(shopping,),
)

print(registry.summary())
```

`GalaxyRegistry` exposes read-only mapping views and convenience methods such as
`get_planet()`, `circles_for_planet()`, `resolve()`, and `solar_system()`.

### Let the builder derive Circle membership

For application code that already declares `circle_ids` on every member,
`GalaxyBuilder` avoids repeating the same references in `Circle.members`:

```python
from easy_agents.galaxy import GalaxyBuilder

registry = (
    GalaxyBuilder()
    .add(personal)
    .add(Circle(id="home", display_name="Home", purpose="Household work"))
    .add(pantry_planner)
    .add(household_coordinator)
    .add(capability)
    .add(inventory)
    .add(vault)
    .add(shopping_playbook)
    .add(gate)
    .add(local_model)
    .add(shopping)
    .build()
)
```

The builder derives only membership. It does not invent permissions,
dependencies, Galaxy ownership, or external access.

## 11. Route and execute a Mission

```python
mission = Mission(
    objective="Plan next week's groceries from current inventory.",
    requested_effects=("read", "draft"),
    requested_vault_ids=("home_vault",),
    team_size=1,
)

trajectory = Wormhole(registry).route(mission)
print(trajectory.planet_ids)

runner = PlanetRunner(registry)

def plan_groceries(work_order):
    # Call your graph, deterministic workflow, local model, or application
    # service here. The Work Order already contains a narrowed grant.
    return f"Prepared a bounded plan for: {work_order.objective}"

runner.register("pantry_planner", plan_groceries)
runtime = GalaxyRuntime(registry, runner=runner)
result = runtime.run(mission)
print(result.synthesis)
```

`PlanetRunner` refuses unregistered handlers and Work Orders that exceed the
Planet's Charter. The current runtime enforces `team_size <= max_planets`;
`MissionBudget` also records timeout, Satellite-call, model-token, and
delegation-depth ceilings for durable runtime integrations. Those additional
counters are not yet consumed by this small synchronous runtime. Use your
application policy layer to issue approval-bound Permission Grants before real
external effects.

To invoke an existing technical tool through canonical policy checks, compose
`SatelliteExecutor(registry, tool_executor)`. Its `invoke()` method verifies the
Planet Charter, Work Order grant, effects, approval state, network policy, and
JSON payload size before calling `ToolExecutor`. It intentionally does not
implement timeouts, retries, or cancellation; a durable host runtime must apply
those controls using the Satellite metadata.

## 12. Load and save YAML

```python
from easy_agents.galaxy import dump_galaxy, load_galaxy, save_galaxy

save_galaxy(registry, "my-galaxy.yaml")
restored = load_galaxy("my-galaxy.yaml")
yaml_text = dump_galaxy(restored)
```

The current canonical schema version is `2`. Unknown fields and unsupported
versions fail closed. The complete example is available at
[`examples/galaxy/minimal_galaxy.yaml`](../../examples/galaxy/minimal_galaxy.yaml).

Validate and route it from the command line:

```bash
easy-agents-galaxy validate \
  --catalog examples/galaxy/minimal_galaxy.yaml

easy-agents-galaxy route \
  --catalog examples/galaxy/minimal_galaxy.yaml \
  "plan next week's groceries"
```

Inspect the current version-1 fleet through the read-only adapter:

```bash
easy-agents-galaxy validate --current-fleet
```

## Version-2 local APIs

When the Control Room service is running:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v2/galaxy` | Complete canonical snapshot |
| `GET /api/v2/topology` | Canonical topology without legacy graph kinds |
| `GET /api/v2/galaxies/{id}` | One Galaxy aggregate |
| `GET /api/v2/circles` | All Circles and member references |
| `GET /api/v2/planets` | Rocky and Giant Planets with Charters |
| `GET /api/v2/satellites` | Satellite policy and operability metadata |
| `GET /api/v2/rogue-stars` | External shared resources |
| `POST /api/v2/wormhole/route` | Route a Mission without executing effects |

Version-1 endpoints remain available during migration.

## Migrating the existing fleet

```python
from easy_agents.fleet import FleetRegistry
from easy_agents.galaxy import registry_from_fleet

canonical = registry_from_fleet(FleetRegistry.default())
```

The adapter currently produces 70 Rocky Planets and preserves identifiers such
as `specialist:personal_steward` and `tool:memory_search` in `legacy_ids`. Mac
Gemma becomes a Rogue Star. The adapter reads v1 data and does not modify it.

## Safety checklist before real effects

- Keep local development APIs on loopback until authentication and Galaxy
  selection are enforced.
- Put policy checks before Satellite, Vault, model, network, and delegation
  operations—not only during planning.
- Bind approvals to exact parameters, principal, Mission, Work Order, expiry,
  and a single-use nonce.
- Configure timeouts, cancellation, payload limits, idempotency, and bounded
  retries for every Satellite.
- Treat retrieved data and model output as untrusted input.
- Redact sensitive content before persistence, SSE streaming, replay, or export.
- Test backup, restore, migration dry-run, and rollback on copied fixtures.

See [Galaxy Domain API](../reference/galaxy-domain-api.md) for a concise class
reference and [Galaxy Terminology](../architecture/galaxy-terminology.md) for
the canonical definitions.
