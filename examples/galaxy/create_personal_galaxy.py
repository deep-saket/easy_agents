"""Created: 2026-09-24

Purpose: Demonstrates constructing, routing, and running a minimal personal Galaxy.
"""

from __future__ import annotations

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


def build_registry() -> GalaxyRegistry:
    """Builds a complete one-Circle example with validated dependencies."""

    capability = Component(
        id="plan_shopping",
        display_name="Plan Shopping",
        description="Builds a bounded grocery plan.",
        circle_ids=("home",),
        status=LifecycleStatus.ACTIVE,
        component_kind=ComponentKind.CAPABILITY,
        capability_ids=("plan_shopping",),
    )
    inventory = Satellite(
        id="inventory_lookup",
        display_name="Inventory Lookup",
        description="Reads pantry inventory.",
        circle_ids=("home",),
        status=LifecycleStatus.ACTIVE,
        tool_id="inventory_lookup",
        effects=("read",),
    )
    vault = Vault(
        id="home_vault",
        display_name="Home Vault",
        description="Stores household preferences.",
        circle_ids=("home",),
        status=LifecycleStatus.ACTIVE,
        sensitivity="private",
    )
    playbook = Component(
        id="shopping_plan",
        display_name="Shopping Plan",
        description="Orders safe planning steps.",
        circle_ids=("home",),
        status=LifecycleStatus.ACTIVE,
        component_kind=ComponentKind.PLAYBOOK,
    )
    gate = Gate(
        id="purchase_gate",
        display_name="Purchase Gate",
        description="Requires approval before a purchase.",
        circle_ids=("home",),
        status=LifecycleStatus.ACTIVE,
        allowed_effects=("read", "draft"),
        approval_effects=("purchase",),
    )
    model = RogueStar(
        id="local_model",
        display_name="Local Model",
        description="Shared loopback inference service.",
        resource_kind=ResourceKind.MODEL,
        endpoint="http://127.0.0.1:8080/v1/completions",
        model_name="example-model",
    )
    planet = RockyPlanet(
        id="pantry_planner",
        display_name="Pantry Planner",
        description="Specialist for groceries and pantry planning.",
        circle_ids=("home",),
        status=LifecycleStatus.ACTIVE,
        tags=("groceries", "pantry"),
        charter=Charter(
            purpose="Plan household shopping without placing an order.",
            capability_ids=(capability.id,),
            satellite_ids=(inventory.id,),
            vault_ids=(vault.id,),
            playbook_ids=(playbook.id,),
            gate_ids=(gate.id,),
            model_ids=(model.id,),
            allowed_effects=("read", "draft"),
        ),
        expertise=("grocery planning", "inventory"),
        specialization_boundary="Plans lists but never purchases products.",
    )
    home = Circle(
        id="home",
        display_name="Home",
        purpose="Coordinates household responsibilities.",
        members=(
            EntityRef(kind=EntityKind.PLANET, id=planet.id),
            EntityRef(kind=EntityKind.COMPONENT, id=capability.id),
            EntityRef(kind=EntityKind.SATELLITE, id=inventory.id),
            EntityRef(kind=EntityKind.COMPONENT, id=vault.id),
            EntityRef(kind=EntityKind.COMPONENT, id=playbook.id),
            EntityRef(kind=EntityKind.COMPONENT, id=gate.id),
        ),
    )
    personal = Galaxy(
        id="personal",
        display_name="Personal Galaxy",
        description="Minimal personal-assistant Galaxy.",
        circle_ids=(home.id,),
        external_access=(
            AccessOrbit(
                galaxy_id="personal",
                rogue_star_id=model.id,
                allowed_effects=("inference",),
                allowed_hosts=("127.0.0.1",),
            ),
        ),
        default=True,
    )
    return GalaxyRegistry(
        galaxies=(personal,),
        circles=(home,),
        planets=(planet,),
        components=(capability, vault, playbook, gate),
        satellites=(inventory,),
        rogue_stars=(model,),
    )


def main() -> None:
    """Routes and executes a safe no-side-effect grocery-planning Mission."""

    registry = build_registry()
    runner = PlanetRunner(registry)
    runner.register(
        "pantry_planner",
        lambda order: f"Prepared a bounded plan for: {order.objective}",
    )
    result = GalaxyRuntime(registry, runner=runner).run(
        Mission(
            objective="Plan next week's groceries.",
            requested_effects=("read", "draft"),
            requested_vault_ids=("home_vault",),
        )
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
