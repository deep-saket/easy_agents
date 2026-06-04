"""FastAPI entrypoint for the conversation manager wrapper."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agents.collection_agent.conversation_manager.runtime import ConversationManagedRuntime


def create_app(
    base_dir: Path | None = None,
    *,
    collection_base_dir: Path | None = None,
) -> FastAPI:
    from agents.collection_agent.ui.server import STATIC_DIR, create_router

    resolved_base_dir = (base_dir or Path(__file__).resolve().parent).resolve()
    runtime = ConversationManagedRuntime.create(
        base_dir=resolved_base_dir,
        collection_base_dir=collection_base_dir,
    )

    app = FastAPI(title="Conversation Manager Debug UI")
    app.include_router(create_router(runtime))
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="collection-agent-ui-static")

    @app.get("/")
    async def home() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.on_event("shutdown")
    async def _shutdown_voice_runtime() -> None:
        runtime.stop_voice_call(force=True)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8061)
