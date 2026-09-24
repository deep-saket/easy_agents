"""Created: 2026-09-24

Purpose: Exposes the public terminology-first API for building agent Galaxies.

The package is intentionally infrastructure-neutral. Applications compose
immutable domain objects, validate them through :class:`GalaxyRegistry`, route
Missions through :class:`Wormhole`, and attach execution through
:class:`PlanetRunner`. Existing v1 fleets can migrate with
:func:`registry_from_fleet` without changing their persisted identifiers.
"""

from easy_agents.galaxy.charters import Charter
from easy_agents.galaxy.catalog import dump_galaxy, load_galaxy, load_galaxy_text, save_galaxy
from easy_agents.galaxy.builder import GalaxyBuilder
from easy_agents.galaxy.circles import Circle
from easy_agents.galaxy.compatibility import registry_from_fleet
from easy_agents.galaxy.constellations import Constellation, Orbit
from easy_agents.galaxy.enums import (
    ComponentKind,
    EntityKind,
    LifecycleStatus,
    MemberKind,
    MissionStatus,
    OrbitKind,
    PlanetClass,
    ResourceKind,
)
from easy_agents.galaxy.galaxies import Galaxy
from easy_agents.galaxy.identity import EntityRef
from easy_agents.galaxy.members import CircleMember, Component
from easy_agents.galaxy.missions import (
    Crew,
    FlightPlan,
    GalaxyMissionResult,
    Mission,
    MissionBudget,
    PermissionGrant,
    PlanetRunResult,
    Trajectory,
    WorkOrder,
)
from easy_agents.galaxy.operations import Gate, MissionLog, MissionLogEntry, Observatory, Vault
from easy_agents.galaxy.planets import GiantPlanet, Planet, RockyPlanet
from easy_agents.galaxy.registry import GalaxyRegistry
from easy_agents.galaxy.rogue_stars import AccessOrbit, RogueStar
from easy_agents.galaxy.routing import Portal, PortalRequest, Wormhole
from easy_agents.galaxy.runtime import GalaxyRuntime, PlanetHandler, PlanetRunner
from easy_agents.galaxy.satellites import Satellite, ToolLike
from easy_agents.galaxy.satellite_runtime import (
    SatelliteCall,
    SatelliteExecutor,
    ToolExecutorLike,
)
from easy_agents.galaxy.schemas import (
    GalaxySnapshotV2,
    GalaxyTopologyV2,
    TopologyNodeV2,
    TopologyOrbitV2,
)
from easy_agents.galaxy.solar_systems import SolarSystem
from easy_agents.galaxy.topology import build_topology
from easy_agents.galaxy.terminology import TERMINOLOGY, TerminologyEntry, terminology_by_term

__all__ = [
    "AccessOrbit",
    "Charter",
    "Circle",
    "CircleMember",
    "Component",
    "ComponentKind",
    "Constellation",
    "Crew",
    "EntityKind",
    "EntityRef",
    "FlightPlan",
    "Galaxy",
    "GalaxyBuilder",
    "GalaxyMissionResult",
    "GalaxyRegistry",
    "GalaxyRuntime",
    "GalaxySnapshotV2",
    "GalaxyTopologyV2",
    "Gate",
    "GiantPlanet",
    "LifecycleStatus",
    "MemberKind",
    "Mission",
    "MissionBudget",
    "MissionLog",
    "MissionLogEntry",
    "MissionStatus",
    "Observatory",
    "Orbit",
    "OrbitKind",
    "PermissionGrant",
    "Planet",
    "PlanetClass",
    "PlanetHandler",
    "PlanetRunResult",
    "PlanetRunner",
    "Portal",
    "PortalRequest",
    "ResourceKind",
    "RockyPlanet",
    "RogueStar",
    "Satellite",
    "SatelliteCall",
    "SatelliteExecutor",
    "SolarSystem",
    "ToolLike",
    "ToolExecutorLike",
    "TopologyNodeV2",
    "TopologyOrbitV2",
    "TERMINOLOGY",
    "TerminologyEntry",
    "Trajectory",
    "Vault",
    "WorkOrder",
    "Wormhole",
    "build_topology",
    "dump_galaxy",
    "load_galaxy",
    "load_galaxy_text",
    "registry_from_fleet",
    "save_galaxy",
    "terminology_by_term",
]
