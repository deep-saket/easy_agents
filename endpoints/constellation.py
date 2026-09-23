"""Local Galaxy knowledge-graph UI and API application."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from easy_agents.constellation.api import create_app as create_constellation_api
from easy_agents.constellation.directory import ConstellationDirectory
from easy_agents.observability import ObservabilityPipeline


STATIC_DIR = Path(__file__).parent / "static" / "constellation"


def create_app(
    directory: ConstellationDirectory | None = None,
    observability: ObservabilityPipeline | None = None,
    gemma_client: Any | None = None,
) -> FastAPI:
    """Creates the standalone local Control Room graph application."""

    app = create_constellation_api(
        directory,
        observability=observability or ObservabilityPipeline.default(),
        gemma_client=gemma_client,
    )
    app.title = "Easy Agents Galaxy Map"
    app.mount(
        "/static",
        StaticFiles(directory=STATIC_DIR),
        name="constellation-static",
    )

    @app.get("/", include_in_schema=False)
    async def home() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
