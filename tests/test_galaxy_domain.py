"""Tests for the terminology-first Galaxy domain and v1 compatibility bridge."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import easy_agents.galaxy as galaxy_api
from easy_agents.constellation.api import create_app
from easy_agents.fleet import FleetRegistry
from easy_agents.galaxy import (
    AccessOrbit,
    Charter,
    Circle,
    Component,
    ComponentKind,
    Constellation,
    EntityKind,
    EntityRef,
    Galaxy,
    GalaxyBuilder,
    GalaxyRegistry,
    GalaxyRuntime,
    GalaxySnapshotV2,
    GalaxyTopologyV2,
    Gate,
    GiantPlanet,
    LifecycleStatus,
    Mission,
    Orbit,
    OrbitKind,
    PermissionGrant,
    Planet,
    PlanetClass,
    PlanetRunner,
    ResourceKind,
    RockyPlanet,
    RogueStar,
    Satellite,
    SatelliteCall,
    SatelliteExecutor,
    TERMINOLOGY,
    TopologyNodeV2,
    TopologyOrbitV2,
    Vault,
    Wormhole,
    build_topology,
    dump_galaxy,
    load_galaxy_text,
    registry_from_fleet,
)
from easy_agents.galaxy.cli import main as galaxy_cli


def _custom_registry() -> GalaxyRegistry:
    """Builds a small but complete Galaxy for reusable domain tests."""

    capability = Component(
        id="plan_shopping",
        display_name="Plan Shopping",
        description="Builds a bounded shopping plan.",
        circle_ids=("home",),
        status=LifecycleStatus.ACTIVE,
        component_kind=ComponentKind.CAPABILITY,
        capability_ids=("plan_shopping",),
    )
    satellite = Satellite(
        id="inventory_lookup",
        display_name="Inventory Lookup",
        description="Reads the current pantry inventory.",
        circle_ids=("home",),
        status=LifecycleStatus.ACTIVE,
        tool_id="inventory_lookup",
        effects=("read",),
    )
    vault = Vault(
        id="home_vault",
        display_name="Home Vault",
        description="Stores household information.",
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
    charter = Charter(
        purpose="Plan household shopping without placing orders.",
        capability_ids=("plan_shopping",),
        satellite_ids=("inventory_lookup",),
        vault_ids=("home_vault",),
        playbook_ids=("shopping_plan",),
        gate_ids=("purchase_gate",),
        model_ids=("local_model",),
        allowed_effects=("read", "draft"),
    )
    rocky = RockyPlanet(
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
    giant = GiantPlanet(
        id="household_coordinator",
        display_name="Household Coordinator",
        description="Coordinates broad household requests.",
        circle_ids=("home",),
        status=LifecycleStatus.ACTIVE,
        tags=("home", "coordination"),
        charter=charter,
        coordination_domains=("home", "life admin"),
        delegation_targets=("pantry_planner",),
    )
    refs = (
        EntityRef(kind=EntityKind.PLANET, id=rocky.id),
        EntityRef(kind=EntityKind.PLANET, id=giant.id),
        EntityRef(kind=EntityKind.COMPONENT, id=capability.id),
        EntityRef(kind=EntityKind.SATELLITE, id=satellite.id),
        EntityRef(kind=EntityKind.COMPONENT, id=vault.id),
        EntityRef(kind=EntityKind.COMPONENT, id=playbook.id),
        EntityRef(kind=EntityKind.COMPONENT, id=gate.id),
    )
    circle = Circle(
        id="home",
        display_name="Home",
        purpose="Coordinates household responsibilities.",
        members=refs,
        tags=("household",),
    )
    rogue_star = RogueStar(
        id="local_model",
        display_name="Local Model",
        description="Shared loopback inference service.",
        resource_kind=ResourceKind.MODEL,
        endpoint="http://127.0.0.1:8080/v1/completions",
        model_name="example-model",
    )
    access = AccessOrbit(
        galaxy_id="personal",
        rogue_star_id=rogue_star.id,
        allowed_effects=("inference",),
        allowed_hosts=("127.0.0.1",),
    )
    galaxy = Galaxy(
        id="personal",
        display_name="Personal Galaxy",
        description="A small example Galaxy.",
        circle_ids=(circle.id,),
        external_access=(access,),
        default=True,
    )
    constellation = Constellation(
        id="shopping",
        display_name="Shopping Constellation",
        circle_ids=(circle.id,),
        nodes=(refs[0], refs[3]),
        orbits=(
            Orbit(
                id="pantry-satellite",
                source=refs[0],
                target=refs[3],
                kind=OrbitKind.CAN_USE,
                label="can use",
            ),
        ),
    )
    return GalaxyRegistry(
        galaxies=(galaxy,),
        circles=(circle,),
        planets=(rocky, giant),
        components=(capability, vault, playbook, gate),
        satellites=(satellite,),
        rogue_stars=(rogue_star,),
        constellations=(constellation,),
    )


def test_custom_registry_routes_and_runs_both_planet_classes() -> None:
    registry = _custom_registry()
    runner = PlanetRunner(registry)
    runner.register("pantry_planner", lambda order: f"planned {order.objective}")
    runner.register("household_coordinator", lambda order: f"coordinated {order.objective}")
    runtime = GalaxyRuntime(registry, runner=runner)

    rocky_result = runtime.run(
        Mission(
            objective="plan grocery inventory",
            preferred_planet_id="pantry_planner",
            requested_vault_ids=("home_vault",),
        )
    )
    giant_result = runtime.run(
        Mission(
            objective="coordinate household work",
            preferred_planet_id="household_coordinator",
        )
    )

    assert rocky_result.trajectory.planet_ids == ("pantry_planner",)
    assert rocky_result.results[0].response.startswith("planned")
    assert giant_result.trajectory.planet_ids == ("household_coordinator",)
    assert giant_result.results[0].response.startswith("coordinated")


def test_builder_derives_symmetric_circle_membership() -> None:
    source = _custom_registry()
    builder = GalaxyBuilder()
    builder.add(source.get_galaxy("personal"))
    builder.add(
        source.get_circle("home").model_copy(update={"members": ()})
    )
    for collection in (
        source.planets,
        source.components,
        source.satellites,
        source.rogue_stars,
        source.constellations,
    ):
        for entity in collection.values():
            builder.add(entity)

    rebuilt = builder.build()

    assert len(rebuilt.get_circle("home").members) == 7
    assert rebuilt.summary() == source.summary()


def test_permission_grants_and_delegation_only_narrow() -> None:
    parent = PermissionGrant(
        effects=("read", "draft"),
        vault_ids=("home_vault",),
        satellite_ids=("inventory_lookup",),
        allow_network=False,
    )
    child = parent.narrowed_to(effects=("read",), allow_network=True)

    assert child.effects == ("read",)
    assert child.allow_network is False
    assert child.is_subset_of(parent)


def test_satellite_rejects_unsafe_automatic_retry() -> None:
    with pytest.raises(ValueError, match="non-idempotent"):
        Satellite(
            id="send_message",
            display_name="Send Message",
            circle_ids=("home",),
            tool_id="send_message",
            effects=("external_send",),
            idempotent=False,
            max_attempts=2,
        )


def test_satellite_executor_enforces_charter_grant_and_payload_limits() -> None:
    class FakeExecutor:
        def execute(self, tool_name: str, input: dict) -> dict:
            return {"tool_name": tool_name, "output": input}

    registry = _custom_registry()
    executor = SatelliteExecutor(registry, FakeExecutor(), max_payload_bytes=128)
    call = SatelliteCall(
        planet_id="pantry_planner",
        satellite_id="inventory_lookup",
        arguments={"location": "pantry"},
    )
    allowed = PermissionGrant(
        effects=("read",),
        satellite_ids=("inventory_lookup",),
    )

    assert executor.invoke(call, grant=allowed)["tool_name"] == "inventory_lookup"
    with pytest.raises(PermissionError, match="denies Satellite"):
        executor.invoke(call, grant=PermissionGrant(effects=("read",)))
    with pytest.raises(ValueError, match="payload exceeds"):
        executor.invoke(
            call.model_copy(update={"arguments": {"value": "x" * 200}}),
            grant=allowed,
        )


def test_rogue_star_access_is_allowlisted_and_loopback_safe() -> None:
    orbit = _custom_registry().get_galaxy("personal").external_access[0]

    assert orbit.allows(
        endpoint="http://127.0.0.1:8080/v1/completions",
        effect="inference",
    )
    assert not orbit.allows(
        endpoint="https://example.com/v1/completions",
        effect="inference",
    )
    assert not orbit.allows(
        endpoint="http://127.0.0.1:8080/v1/completions",
        effect="write",
    )


def test_constellation_rejects_disconnected_graph() -> None:
    with pytest.raises(ValueError, match="connected graph"):
        Constellation(
            id="broken",
            display_name="Broken",
            circle_ids=("home",),
            nodes=(
                EntityRef(kind=EntityKind.PLANET, id="one"),
                EntityRef(kind=EntityKind.PLANET, id="two"),
            ),
        )


def test_snapshot_yaml_round_trip_preserves_planet_subclasses() -> None:
    registry = _custom_registry()
    snapshot = GalaxySnapshotV2.from_registry(registry)
    restored = load_galaxy_text(dump_galaxy(registry))

    assert snapshot.version == 2
    assert isinstance(restored.get_planet("pantry_planner"), RockyPlanet)
    assert isinstance(restored.get_planet("household_coordinator"), GiantPlanet)
    assert isinstance(restored.get_component("home_vault"), Vault)
    assert isinstance(restored.get_component("purchase_gate"), Gate)
    assert restored.summary() == registry.summary()


def test_models_forbid_unknown_configuration_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        Mission.model_validate({"objective": "plan groceries", "surprise": True})


def test_registry_requires_a_concrete_planet_subclass() -> None:
    source = _custom_registry()
    rocky = source.get_planet("pantry_planner")
    bare_planet = Planet(
        id=rocky.id,
        display_name=rocky.display_name,
        description=rocky.description,
        circle_ids=rocky.circle_ids,
        status=rocky.status,
        charter=rocky.charter,
        planet_class=PlanetClass.ROCKY,
    )

    with pytest.raises(ValueError, match="RockyPlanet or GiantPlanet"):
        GalaxyRegistry(
            galaxies=source.galaxies.values(),
            circles=source.circles.values(),
            planets=(bare_planet, source.get_planet("household_coordinator")),
            components=source.components.values(),
            satellites=source.satellites.values(),
            rogue_stars=source.rogue_stars.values(),
            constellations=source.constellations.values(),
        )


def test_registry_keeps_constellations_inside_declared_circles() -> None:
    source = _custom_registry()
    invalid_overlay = Constellation(
        id="outside",
        display_name="Outside",
        circle_ids=("home",),
        nodes=(EntityRef(kind=EntityKind.GALAXY, id="personal"),),
    )

    with pytest.raises(ValueError, match="cannot contain 'galaxy'"):
        GalaxyRegistry(
            galaxies=source.galaxies.values(),
            circles=source.circles.values(),
            planets=source.planets.values(),
            components=source.components.values(),
            satellites=source.satellites.values(),
            rogue_stars=source.rogue_stars.values(),
            constellations=(invalid_overlay,),
        )


def test_v1_adapter_preserves_all_current_roles_and_technical_ids() -> None:
    registry = registry_from_fleet(FleetRegistry.default())

    assert registry.summary() == {
        "galaxies": 1,
        "circles": 14,
        "planets": 70,
        "components": 51,
        "satellites": 11,
        "rogue_stars": 1,
        "constellations": 1,
    }
    assert "specialist:personal_steward" in registry.get_planet(
        "personal_steward"
    ).legacy_ids
    assert "tool:memory_search" in registry.satellites["memory_search"].legacy_ids
    assert registry.rogue_stars["mac_gemma"].model_name == "gemma-4-E4B"


def test_canonical_topology_uses_new_terms_and_wormhole_route() -> None:
    registry = _custom_registry()
    topology = build_topology(registry)
    kinds = {item.kind for item in topology.nodes}
    trajectory = Wormhole(registry).route(
        Mission(objective="plan grocery inventory", preferred_planet_id="pantry_planner")
    )

    assert {"wormhole", "galaxy", "circle", "rocky_planet", "giant_planet", "satellite", "rogue_star"} <= kinds
    assert [item.kind for item in trajectory.path] == [
        EntityKind.WORMHOLE,
        EntityKind.GALAXY,
        EntityKind.CIRCLE,
        EntityKind.PLANET,
    ]


def test_topology_rejects_dangling_orbits() -> None:
    with pytest.raises(ValidationError, match="dangling Orbit endpoints"):
        GalaxyTopologyV2(
            nodes=(
                TopologyNodeV2(id="galaxy:personal", kind="galaxy", label="Personal"),
            ),
            orbits=(
                TopologyOrbitV2(
                    id="broken",
                    source="galaxy:personal",
                    target="circle:missing",
                    kind="contains",
                    label="contains",
                ),
            ),
            counts={"galaxy": 1},
        )


def test_v2_api_is_additive_and_routes_canonical_missions() -> None:
    client = TestClient(create_app())

    snapshot = client.get("/api/v2/galaxy")
    satellites = client.get("/api/v2/satellites")
    route = client.post(
        "/api/v2/wormhole/route",
        json={"objective": "calculate a satellite RF link budget"},
    )

    assert snapshot.status_code == 200
    assert snapshot.json()["version"] == 2
    assert len(snapshot.json()["planets"]) == 70
    assert satellites.status_code == 200
    assert any(item["id"] == "memory_search" for item in satellites.json())
    assert route.status_code == 200
    assert route.json()["circle_ids"] == ["satcom"]
    assert route.json()["planet_ids"] == ["rf_link_budget_specialist"]


def test_galaxy_cli_validates_and_routes_example_catalog(capsys) -> None:
    path = "examples/galaxy/minimal_galaxy.yaml"

    assert galaxy_cli(["validate", "--catalog", path]) == 0
    validation = capsys.readouterr().out
    assert '"status": "valid"' in validation
    assert galaxy_cli(["route", "--catalog", path, "plan groceries"]) == 0
    route = capsys.readouterr().out
    assert '"planet_ids"' in route
    assert '"pantry_planner"' in route


def test_public_galaxy_classes_are_documented_and_modules_have_headers() -> None:
    package_root = Path(inspect.getfile(galaxy_api)).parent
    public_classes = [
        value
        for name in galaxy_api.__all__
        if inspect.isclass(value := getattr(galaxy_api, name, None))
        and value.__module__.startswith("easy_agents.galaxy")
    ]

    assert public_classes
    assert all(inspect.getdoc(value) for value in public_classes)
    for path in package_root.glob("*.py"):
        header = path.read_text(encoding="utf-8").splitlines()[:5]
        assert any("Created:" in line for line in header), path
        assert any("Purpose:" in line for line in header), path


def test_terminology_matrix_points_to_public_contracts() -> None:
    required = {
        "Galaxy",
        "Circle",
        "Planet",
        "Rocky Planet",
        "Giant Planet",
        "Component",
        "Satellite",
        "Constellation",
        "Solar System",
        "Wormhole",
        "Rogue Star",
    }

    assert required <= {item.term for item in TERMINOLOGY}
    assert len(TERMINOLOGY) == len({item.term for item in TERMINOLOGY})
    assert all(item.contract in galaxy_api.__all__ for item in TERMINOLOGY)
