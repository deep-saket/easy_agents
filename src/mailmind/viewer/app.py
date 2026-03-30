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

    @app.get("/emails", response_class=HTMLResponse)
    def emails(request: Request, search: str | None = Query(default=None)) -> HTMLResponse:
        messages = active_container.repository.list_messages(search=search)
        return templates.TemplateResponse(
            request,
            "inbox.html",
            {"request": request, "title": "Emails", "messages": messages, "search": search or ""},
        )

    @app.get("/important", response_class=HTMLResponse)
    def important(request: Request, search: str | None = Query(default=None)) -> HTMLResponse:
        messages = active_container.repository.list_messages(search=search, only_important=True)
        return templates.TemplateResponse(
            request,
            "important.html",
            {"request": request, "title": "Important", "messages": messages, "search": search or ""},
        )

    @app.get("/search", response_class=HTMLResponse)
    def search(request: Request, query: str | None = Query(default=None), category: str | None = Query(default=None), sender: str | None = Query(default=None)) -> HTMLResponse:
        messages = active_container.repository.search_messages(query=query, category=category, sender=sender, limit=100)
        return templates.TemplateResponse(
            request,
            "search.html",
            {
                "request": request,
                "title": "Search",
                "messages": messages,
                "query": query or "",
                "category": category or "",
                "sender": sender or "",
            },
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
        tool_logs = active_container.repository.list_tool_logs(limit=100)
        return templates.TemplateResponse(
            request,
            "logs.html",
            {"request": request, "title": "Logs", "logs": entries, "tool_logs": tool_logs},
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

    @app.get("/api/tools")
    def api_tools() -> list[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema.__name__,
                "output_schema": tool.output_schema.__name__,
            }
            for tool in active_container.tool_registry.list_tools()
        ]

    @app.get("/api/tool-logs")
    def api_tool_logs(limit: int = Query(default=100)) -> list[dict]:
        return [entry.model_dump(mode="json") for entry in active_container.repository.list_tool_logs(limit=limit)]

    @app.get("/api/agent/run")
    def api_agent_run(query: str) -> dict:
        return active_container.agent.run(query)

    return app
