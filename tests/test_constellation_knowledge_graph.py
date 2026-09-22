"""Tests for the reusable Constellation knowledge-graph projection."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from easy_agents.constellation import (
    KnowledgeGraph,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    build_knowledge_graph,
)
from easy_agents.constellation.api import create_app as create_api_app
from endpoints.constellation import create_app as create_ui_app


def test_knowledge_graph_contains_roster_and_shared_components() -> None:
    graph = build_knowledge_graph()
    nodes = {node.id: node for node in graph.nodes}

    assert graph.counts["specialist"] >= 60
    assert graph.counts["guild"] >= 10
    assert nodes["specialist:personal_steward"].status == "active"
    assert nodes["specialist:opportunity_portfolio_steward"].status == "planned"
    assert nodes["tool:memory_search"].status == "implemented"
    assert nodes["memory:employer_authorized"].kind == "memory"
    assert nodes["playbook:opportunity_validation"].kind == "playbook"
    assert nodes["model:mac_gemma"].metadata["context_tokens"] == 16_384


def test_knowledge_graph_relationships_have_valid_endpoints() -> None:
    graph = build_knowledge_graph()
    node_ids = {node.id for node in graph.nodes}
    edge_ids = {edge.id for edge in graph.edges}

    assert len(edge_ids) == len(graph.edges)
    assert all(edge.source in node_ids for edge in graph.edges)
    assert all(edge.target in node_ids for edge in graph.edges)
    assert any(
        edge.source == "specialist:employment_boundary_guardian"
        and edge.target == "specialist:opportunity_portfolio_steward"
        and edge.kind == "guards"
        for edge in graph.edges
    )
    assert any(
        edge.source == "tool:email_send"
        and edge.target == "capability:communications.send"
        for edge in graph.edges
    )


def test_knowledge_graph_rejects_duplicate_nodes_and_dangling_edges() -> None:
    node = KnowledgeGraphNode(id="service:runtime", kind="service", label="Runtime")

    with pytest.raises(ValueError, match="Duplicate knowledge-graph node"):
        KnowledgeGraph(nodes=[node, node], edges=[], counts={"service": 2})

    with pytest.raises(ValueError, match="unknown nodes"):
        KnowledgeGraph(
            nodes=[node],
            edges=[
                KnowledgeGraphEdge(
                    id="routes:service:runtime->service:missing",
                    source="service:runtime",
                    target="service:missing",
                    kind="routes",
                    label="routes to",
                )
            ],
            counts={"service": 1},
        )


def test_constellation_api_exposes_knowledge_graph() -> None:
    client = TestClient(create_api_app())

    response = client.get("/api/knowledge-graph")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == 1
    assert payload["counts"]["memory"] >= 4
    assert len(payload["edges"]) > len(payload["nodes"])


def test_constellation_ui_serves_local_assets() -> None:
    client = TestClient(create_ui_app())

    page = client.get("/")
    script = client.get("/static/app.js")
    styles = client.get("/static/styles.css")

    assert page.status_code == 200
    assert "Constellation Map" in page.text
    assert "Find anything" in page.text
    assert script.status_code == 200
    assert "knowledge-graph" in script.text
    assert styles.status_code == 200
    assert "--specialist" in styles.text
