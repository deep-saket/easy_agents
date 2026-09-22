"""Local HTTP API for the constellation Roster and Feature Architect."""

from __future__ import annotations

from fastapi import FastAPI

from easy_agents.constellation.directory import ConstellationDirectory
from easy_agents.constellation.feature_intake import FeatureIntakeService
from easy_agents.constellation.knowledge_graph import build_knowledge_graph
from easy_agents.constellation.models import FeatureProposal, FeatureRequest


def create_app(directory: ConstellationDirectory | None = None) -> FastAPI:
    """Builds the local API consumed by the future Control Room."""

    active_directory = directory or ConstellationDirectory.default()
    architect = FeatureIntakeService(active_directory)
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

        return build_knowledge_graph(active_directory).model_dump(mode="json")

    @app.post("/api/features/assess", response_model=FeatureProposal)
    def assess_feature(request: FeatureRequest) -> FeatureProposal:
        return architect.assess(request)

    return app


app = create_app()
