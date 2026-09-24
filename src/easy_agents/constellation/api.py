"""Local HTTP API for the constellation Roster and Feature Architect."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException

from easy_agents.constellation.directory import ConstellationDirectory
from easy_agents.constellation.feature_intake import FeatureIntakeService
from easy_agents.constellation.knowledge_graph import (
    KnowledgeGraphOverlay,
    build_knowledge_graph,
    load_default_overlay,
)
from easy_agents.constellation.models import FeatureProposal, FeatureRequest
from easy_agents.constellation.operations_api import create_operations_router
from easy_agents.fleet.model_profiles import (
    MAC_GEMMA_PROFILE_ID,
    build_fleet_mac_gemma,
    mac_gemma_status,
)
from easy_agents.fleet.gateway import WORMHOLE_ID
from easy_agents.fleet.models import (
    GalaxyRoutePlan,
    FleetMissionResult,
    FleetValidationReport,
    MissionRequest,
)
from easy_agents.fleet.registry import FleetRegistry
from easy_agents.fleet.runtime import FleetRuntime
from easy_agents.galaxy import (
    GalaxySnapshotV2,
    Mission,
    Trajectory,
    Wormhole,
    build_topology,
    registry_from_fleet,
)
from easy_agents.observability import ObservabilityPipeline


def create_app(
    directory: ConstellationDirectory | None = None,
    observability: ObservabilityPipeline | None = None,
    gemma_client: Any | None = None,
) -> FastAPI:
    """Builds the local API consumed by the future Control Room."""

    active_directory = directory or ConstellationDirectory.default()
    active_overlay = load_default_overlay() if directory is None else KnowledgeGraphOverlay()
    architect = FeatureIntakeService(active_directory)
    fleet_registry = FleetRegistry.from_constellation(
        directory=active_directory,
        overlay=active_overlay,
    )
    galaxy_registry = registry_from_fleet(fleet_registry)
    galaxy_snapshot = GalaxySnapshotV2.from_registry(galaxy_registry)
    canonical_wormhole = Wormhole(galaxy_registry)
    operations = observability or ObservabilityPipeline.memory()
    active_gemma = gemma_client if gemma_client is not None else build_fleet_mac_gemma()
    fleet_runtime = FleetRuntime(
        registry=fleet_registry,
        models={MAC_GEMMA_PROFILE_ID: active_gemma},
        event_recorder=operations,
    )
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        operations.close()

    app = FastAPI(title="Easy Agents Constellation", lifespan=lifespan)
    app.state.observability = operations
    app.state.galaxy_registry = galaxy_registry
    app.include_router(create_operations_router(operations))

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "catalog_version": active_directory.catalog.version,
            "guilds": len(active_directory.guilds),
            "capabilities": len(active_directory.capabilities),
            "specialists": len(active_directory.specialists),
            "observability": operations.health(),
            "model_profiles": {
                MAC_GEMMA_PROFILE_ID: {"configured": True, "external": True}
            },
            "entrypoint": WORMHOLE_ID,
            "galaxy": "personal",
            "constellations": 1,
        }

    @app.get("/api/models/mac-gemma/status")
    def gemma_status() -> dict[str, object]:
        """Checks Mac-serving readiness without exposing credentials."""

        return mac_gemma_status(active_gemma)

    @app.get("/api/constellation")
    def constellation() -> dict[str, object]:
        return active_directory.catalog.model_dump(mode="json")

    @app.get("/api/knowledge-graph")
    def knowledge_graph() -> dict[str, object]:
        """Returns active Roster entities plus planned reusable components."""

        return build_knowledge_graph(active_directory, active_overlay).model_dump(mode="json")

    @app.get("/api/v2/galaxy", response_model=GalaxySnapshotV2)
    def canonical_galaxy() -> GalaxySnapshotV2:
        """Returns the complete canonical version-2 Galaxy snapshot.

        Version-1 catalog identifiers remain available in each entity's
        ``legacy_ids``. This endpoint is additive and does not alter v1 routes.
        """

        return galaxy_snapshot

    @app.get("/api/v2/topology")
    def canonical_topology() -> dict[str, object]:
        """Returns canonical topology kinds without legacy graph terminology."""

        return build_topology(galaxy_registry).model_dump(mode="json")

    @app.get("/api/v2/galaxies/{galaxy_id}")
    def canonical_galaxy_by_id(galaxy_id: str) -> dict[str, object]:
        """Returns one canonical Galaxy ownership aggregate."""

        try:
            return galaxy_registry.get_galaxy(galaxy_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v2/circles")
    def canonical_circles() -> list[dict[str, object]]:
        """Lists canonical Circles in stable identifier order."""

        return [
            galaxy_registry.circles[item].model_dump(mode="json")
            for item in sorted(galaxy_registry.circles)
        ]

    @app.get("/api/v2/planets")
    def canonical_planets() -> list[dict[str, object]]:
        """Lists Rocky and Giant Planets with their complete Charters."""

        return [
            galaxy_registry.planets[item].model_dump(mode="json")
            for item in sorted(galaxy_registry.planets)
        ]

    @app.get("/api/v2/satellites")
    def canonical_satellites() -> list[dict[str, object]]:
        """Lists tool-backed Satellite Components and safety metadata."""

        return [
            galaxy_registry.satellites[item].model_dump(mode="json")
            for item in sorted(galaxy_registry.satellites)
        ]

    @app.get("/api/v2/rogue-stars")
    def canonical_rogue_stars() -> list[dict[str, object]]:
        """Lists external resources that belong to no Galaxy."""

        return [
            galaxy_registry.rogue_stars[item].model_dump(mode="json")
            for item in sorted(galaxy_registry.rogue_stars)
        ]

    @app.post("/api/v2/wormhole/route", response_model=Trajectory)
    def route_canonical_mission(mission: Mission) -> Trajectory:
        """Routes a canonical Mission without executing any Planet or effect."""

        try:
            return canonical_wormhole.route(mission)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/fleet")
    def fleet() -> dict[str, object]:
        """Lists every compiled active or sandboxed Specialist Charter."""

        return {
            "summary": fleet_registry.summary(),
            "specialists": [
                item.model_dump(mode="json")
                for item in fleet_registry.list_specialists()
            ],
        }

    @app.get("/api/fleet/{specialist_id}")
    def specialist(specialist_id: str) -> dict[str, object]:
        """Returns one fully resolved Specialist Charter."""

        try:
            manifest = fleet_registry.get_specialist(specialist_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return manifest.model_dump(mode="json")

    def route_through_wormhole(request: MissionRequest) -> GalaxyRoutePlan:
        """Returns the full Wormhole route without executing a Specialist."""

        try:
            return fleet_runtime.route_plan(request)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    app.post(
        "/api/wormhole/route",
        response_model=GalaxyRoutePlan,
    )(route_through_wormhole)
    app.post(
        "/api/entrypoint/route",
        response_model=GalaxyRoutePlan,
        include_in_schema=False,
    )(route_through_wormhole)
    app.post(
        "/api/missions/route",
        response_model=GalaxyRoutePlan,
    )(route_through_wormhole)

    @app.post("/api/missions/run", response_model=FleetMissionResult)
    def run_mission(request: MissionRequest) -> FleetMissionResult:
        """Runs a safe plan or model-backed advisory Mission."""

        try:
            if request.model_id == MAC_GEMMA_PROFILE_ID and not active_gemma.is_ready():
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Mac Gemma is not ready at the configured loopback endpoint. "
                        "Start the external mac-serving service first."
                    ),
                )
            return fleet_runtime.run(request)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/fleet/test", response_model=FleetValidationReport)
    def test_fleet() -> FleetValidationReport:
        """Validates every Specialist in safe, no-model, no-network mode."""

        return fleet_runtime.validate_all()

    @app.post("/api/features/assess", response_model=FeatureProposal)
    def assess_feature(request: FeatureRequest) -> FeatureProposal:
        return architect.assess(request)

    return app


app = create_app()
