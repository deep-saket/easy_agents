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
    assert nodes["specialist:opportunity_portfolio_steward"].status == "sandboxed"
    assert nodes["tool:memory_search"].status == "implemented"
    assert nodes["tool:memory_search"].metadata["topology_role"] == "satellite"
    assert nodes["tool:memory_search"].metadata["canonical_term"] == "Satellite"
    assert nodes["memory:employer_authorized"].kind == "memory"
    assert nodes["playbook:opportunity_validation"].kind == "playbook"
    assert nodes["model:mac_gemma"].metadata["context_tokens"] == 16_384
    assert nodes["model:mac_gemma"].kind == "rogue_star"
    assert nodes["model:mac_gemma"].metadata["resource_kind"] == "model"
    assert nodes["model:mac_gemma"].metadata["galaxy_membership"] == "external"
    assert nodes["model:mac_gemma"].metadata["shared_across_galaxies"] is True
    assert nodes["service:wormhole"].metadata["entrypoint"] is True
    assert nodes["galaxy:personal"].kind == "galaxy"
    assert nodes["constellation:personal_operations"].kind == "constellation"
    assert nodes["constellation:personal_operations"].metadata["routing_layer"] is False
    assert nodes["guild:home"].metadata["member_types"] == [
        "Rocky Planet",
        "Giant Planet",
        "Component",
    ]
    assert nodes["specialist:personal_steward"].metadata["planet_class"] == "rocky_planet"


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
    assert any(
        edge.source == "service:wormhole"
        and edge.target == "galaxy:personal"
        and edge.kind == "enters_galaxy"
        for edge in graph.edges
    )
    assert any(
        edge.source == "galaxy:personal"
        and edge.target == "guild:energy"
        and edge.kind == "contains_circle"
        for edge in graph.edges
    )
    assert any(
        edge.source == "galaxy:personal"
        and edge.target == "model:mac_gemma"
        and edge.kind == "accesses_external"
        and edge.metadata["ownership"] is False
        and edge.metadata["cross_galaxy"] is True
        for edge in graph.edges
    )
    assert any(
        edge.source == "constellation:personal_operations"
        and edge.target == "guild:energy"
        and edge.kind == "spans_circle"
        for edge in graph.edges
    )
    assert any(
        edge.source == "guild:energy"
        and edge.target == "specialist:energy_systems_scout"
        and edge.kind == "dispatches_to"
        and edge.metadata["routing_only"] is True
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
    assert "Personal Agent Galaxy" in page.text
    assert "Find anything" in page.text
    assert "Sandbox mission" in page.text
    assert "Control Room mode" in page.text
    assert ">Guide<" in page.text
    assert "One language for the whole agent system" in page.text
    assert "Circle ≠ Constellation" in page.text
    assert "Rocky ≠ Giant" in page.text
    assert "Planet ≠ Component" in page.text
    assert "Rocky Planet" in page.text
    assert "Giant Planet" in page.text
    assert "Rogue Star" in page.text
    assert "Satellite" in page.text
    assert "Planet ≠ Satellite" in page.text
    assert "Galaxy ≠ Rogue Star" in page.text
    assert "Circle Member" in page.text
    assert "Think in boundaries, connected graphs, and groups" in page.text
    assert "A Solar System is everything a Planet can directly reach" in page.text
    assert "Plan next week’s groceries" in page.text
    assert "Mission execution lifecycle" in page.text
    assert "Execution timeline" in page.text
    assert "Test all 70 planets" in page.text
    assert "Mac Gemma · external local service" in page.text
    assert "What should the Galaxy handle?" in page.text
    assert "Wormhole → Galaxy → Circle → Planet" in page.text
    assert script.status_code == 200
    assert "knowledge-graph" in script.text
    assert "events/stream" in script.text
    assert "rebuildReplay" in script.text
    assert "models/mac-gemma/status" in script.text
    assert "wormhole/route" in script.text
    assert styles.status_code == 200
    assert "--specialist" in styles.text
    assert "--rogue-star" in styles.text
    assert "--satellite" in styles.text
    assert 'tool: "Satellites"' in script.text
