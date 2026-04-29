"""Created: 2026-04-18

Purpose: Runs a local interactive UI for composing agent graphs from reusable nodes.
"""

from __future__ import annotations

from importlib import import_module
from inspect import isclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.graph_builder import (
    GRAPH_MODES,
    NODE_KINDS,
    generate_python_scaffold,
    normalize_graph_payload,
    validate_graph_spec,
)
from src.nodes.base import BaseGraphNode


STATIC_DIR = Path(__file__).parent / "static" / "graph_builder"

DEFAULT_CONFIGS: dict[str, dict[str, Any]] = {
    "tool": {
        "execution_policy": "sync",
        "timeout_ms": 120000,
        "retry_policy": {"max_retries": 1, "backoff_ms": 500},
        "approval_required": False,
    },
    "agent": {
        "delegate_agent": "",
        "session_template": "{session_id}::delegate::{agent_name}",
        "input_template": "{user_input}",
    },
}


class GraphPayload(BaseModel):
    """Request payload wrapper for graph APIs."""

    payload: dict[str, Any]


def _node_catalog() -> list[dict[str, str]]:
    """Builds a small node catalog from shared node exports."""
    module = import_module("src.nodes")
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for symbol_name in getattr(module, "__all__", []):
        symbol = getattr(module, symbol_name, None)
        if not isclass(symbol):
            continue
        if not issubclass(symbol, BaseGraphNode):
            continue
        if symbol_name in {"BaseGraphNode"}:
            continue
        if symbol.__name__ in seen:
            continue
        seen.add(symbol.__name__)
        items.append(
            {
                "id": symbol.__name__,
                "label": symbol.__name__,
                "module": symbol.__module__,
                "description": (symbol.__doc__ or "").strip().split("\n")[0],
                "kind": "node",
                "configurable_fields": [
                    "label",
                    "description",
                    "kind",
                    "tools",
                    "config",
                ],
            }
        )

    items.sort(key=lambda item: item["label"].lower())
    return items


def _agent_catalog() -> list[dict[str, Any]]:
    """Returns the currently known concrete agent types as graph components."""
    return [
        {
            "id": "SimpleConversationAgent",
            "label": "SimpleConversationAgent",
            "module": "agents.simple_conversation.agent",
            "description": "Use this agent runtime as a nested AgentNode component.",
            "kind": "agent",
        },
        {
            "id": "MailMindAgent",
            "label": "MailMindAgent",
            "module": "agents.mailmind.agent",
            "description": "Use this agent runtime as a nested AgentNode component.",
            "kind": "agent",
        },
    ]


def create_graph_builder_router() -> APIRouter:
    """Builds API routes for the graph builder UI."""
    router = APIRouter(prefix="/api", tags=["graph_builder"])

    @router.get("/catalog")
    async def catalog() -> dict[str, Any]:
        return {
            "nodes": _node_catalog(),
            "agents": _agent_catalog(),
            "meta": {
                "graph_modes": list(GRAPH_MODES),
                "node_kinds": list(NODE_KINDS),
                "default_configs": DEFAULT_CONFIGS,
                "tool_capabilities": [
                    {
                        "kind": "tool",
                        "fields": ["execution_policy", "timeout_ms", "retry_policy", "approval_required"],
                    },
                    {
                        "kind": "agent",
                        "fields": ["delegate_agent", "session_template", "input_template"],
                    },
                ],
            },
        }

    @router.post("/validate")
    async def validate_graph(body: GraphPayload) -> dict[str, Any]:
        spec = normalize_graph_payload(body.payload)
        issues = validate_graph_spec(spec)
        errors = [issue for issue in issues if issue.severity == "error"]
        return {
            "ok": len(errors) == 0,
            "issues": [issue.model_dump(mode="json") for issue in issues],
            "normalized": spec.model_dump(mode="json"),
        }

    @router.post("/export/json")
    async def export_json(body: GraphPayload) -> dict[str, Any]:
        spec = normalize_graph_payload(body.payload)
        issues = validate_graph_spec(spec)
        mode = str(spec.graph.get("mode", "graph_of_thought"))
        if mode in {"chain_of_thought", "tree_of_thought"} and any(issue.severity == "error" for issue in issues):
            raise HTTPException(status_code=400, detail={"message": "Graph failed validation.", "issues": [issue.model_dump(mode="json") for issue in issues]})
        return {
            "ok": True,
            "issues": [issue.model_dump(mode="json") for issue in issues],
            "graph": spec.model_dump(mode="json"),
        }

    @router.post("/export/python")
    async def export_python(body: GraphPayload) -> dict[str, Any]:
        spec = normalize_graph_payload(body.payload)
        issues = validate_graph_spec(spec)
        mode = str(spec.graph.get("mode", "graph_of_thought"))
        if mode in {"chain_of_thought", "tree_of_thought"} and any(issue.severity == "error" for issue in issues):
            raise HTTPException(status_code=400, detail={"message": "Graph failed validation.", "issues": [issue.model_dump(mode="json") for issue in issues]})
        return {
            "ok": True,
            "issues": [issue.model_dump(mode="json") for issue in issues],
            "python": generate_python_scaffold(spec),
        }

    return router


def create_app() -> FastAPI:
    """Creates the standalone graph builder app."""
    app = FastAPI(title="Easy Agents Graph Builder")
    app.include_router(create_graph_builder_router())
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="graph-builder-static")

    @app.get("/")
    async def home() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
