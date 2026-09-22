"""Local HTTP API for the constellation Roster and Feature Architect."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from easy_agents.constellation.directory import ConstellationDirectory
from easy_agents.constellation.feature_intake import FeatureIntakeService
from easy_agents.constellation.knowledge_graph import (
    KnowledgeGraphOverlay,
    build_knowledge_graph,
    load_default_overlay,
)
from easy_agents.constellation.models import FeatureProposal, FeatureRequest
from easy_agents.fleet.models import FleetMissionResult, MissionRequest
from easy_agents.fleet.registry import FleetRegistry
from easy_agents.fleet.runtime import FleetRuntime


def create_app(directory: ConstellationDirectory | None = None) -> FastAPI:
    """Builds the local API consumed by the future Control Room."""

    active_directory = directory or ConstellationDirectory.default()
    active_overlay = load_default_overlay() if directory is None else KnowledgeGraphOverlay()
    architect = FeatureIntakeService(active_directory)
    fleet_registry = FleetRegistry.from_constellation(
        directory=active_directory,
        overlay=active_overlay,
    )
    fleet_runtime = FleetRuntime(registry=fleet_registry)
    app = FastAPI(title="Easy Agents Constellation")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "catalog_version": active_directory.catalog.version,
            "guilds": len(active_directory.guilds),
            "capabilities": len(active_directory.capabilities),
            "specialists": len(active_directory.specialists),
        }

    @app.get("/api/constellation")
    def constellation() -> dict[str, object]:
        return active_directory.catalog.model_dump(mode="json")

    @app.get("/api/knowledge-graph")
    def knowledge_graph() -> dict[str, object]:
        """Returns active Roster entities plus planned reusable components."""

        return build_knowledge_graph(active_directory, active_overlay).model_dump(mode="json")

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

    @app.post("/api/missions/route")
    def route_mission(request: MissionRequest) -> dict[str, object]:
        """Returns explainable routing candidates without running a model."""

        return {
            "objective": request.objective,
            "candidates": [
                item.model_dump(mode="json") for item in fleet_runtime.route(request)
            ],
        }

    @app.post("/api/missions/run", response_model=FleetMissionResult)
    def run_mission(request: MissionRequest) -> FleetMissionResult:
        """Runs a deterministic safe plan; no external effects are executed."""

        try:
            return fleet_runtime.run(request)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/features/assess", response_model=FeatureProposal)
    def assess_feature(request: FeatureRequest) -> FeatureProposal:
        return architect.assess(request)

    return app


app = create_app()
