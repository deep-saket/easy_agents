from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from mailmind.container import AppContainer


def create_app(container: AppContainer | None = None) -> FastAPI:
    app = FastAPI(title="mailmind viewer")
    active_container = container or AppContainer.from_env()
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, search: str | None = Query(default=None)) -> HTMLResponse:
        messages = active_container.repository.list_messages(search=search)
        return templates.TemplateResponse(
            request,
            "inbox.html",
            {"request": request, "title": "Inbox", "messages": messages, "search": search or ""},
        )

    @app.get("/important", response_class=HTMLResponse)
    def important(request: Request, search: str | None = Query(default=None)) -> HTMLResponse:
        messages = active_container.repository.list_messages(search=search, only_important=True)
        return templates.TemplateResponse(
            request,
            "important.html",
            {"request": request, "title": "Important", "messages": messages, "search": search or ""},
        )

    @app.get("/approvals", response_class=HTMLResponse)
    def approvals(request: Request) -> HTMLResponse:
        approvals_data = active_container.repository.list_approvals()
        return templates.TemplateResponse(
            request,
            "approvals.html",
            {"request": request, "title": "Needs Approval", "approvals": approvals_data},
        )

    @app.get("/drafts", response_class=HTMLResponse)
    def drafts(request: Request) -> HTMLResponse:
        drafts_data = active_container.repository.list_drafts()
        return templates.TemplateResponse(
            request,
            "drafts.html",
            {"request": request, "title": "Drafts", "drafts": drafts_data},
        )

    @app.get("/logs", response_class=HTMLResponse)
    def logs(request: Request) -> HTMLResponse:
        entries = active_container.audit_log.read_recent()
        return templates.TemplateResponse(
            request,
            "logs.html",
            {"request": request, "title": "Logs", "logs": entries},
        )

    @app.get("/settings", response_class=HTMLResponse)
    def settings(request: Request) -> HTMLResponse:
        policy = active_container.policy_provider.load()
        return templates.TemplateResponse(
            request,
            "settings.html",
            {"request": request, "title": "Settings & Policies", "settings": active_container.settings, "policy": policy},
        )

    @app.get("/api/messages")
    def api_messages(search: str | None = Query(default=None), important: bool = Query(default=False)) -> list[dict]:
        bundles = active_container.repository.list_messages(search=search, only_important=important)
        return [bundle.model_dump(mode="json") for bundle in bundles]

    return app

