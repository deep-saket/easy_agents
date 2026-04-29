"""Tests graph-builder API validation/export behavior."""

from __future__ import annotations

from fastapi.testclient import TestClient

from endpoints.graph_builder import create_app


def _sample_graph(*, mode: str = "graph_of_thought") -> dict:
    return {
        "version": 2,
        "graph": {"mode": mode, "name": "Demo"},
        "nodes": [
            {
                "id": "n1",
                "label": "Thought 1",
                "kind": "thought",
                "module": "",
                "description": "first",
                "tools": [],
                "config": {},
                "position": {"x": 20, "y": 20},
            },
            {
                "id": "n2",
                "label": "Thought 2",
                "kind": "thought",
                "module": "",
                "description": "second",
                "tools": [],
                "config": {},
                "position": {"x": 220, "y": 20},
            },
        ],
        "edges": [
            {
                "id": "e1",
                "source": "n1",
                "target": "n2",
                "source_port": "out",
                "target_port": "in",
                "metadata": {},
            }
        ],
    }


def test_catalog_includes_meta_and_kinds() -> None:
    client = TestClient(create_app())

    response = client.get("/api/catalog")
    assert response.status_code == 200
    payload = response.json()

    assert "nodes" in payload
    assert "agents" in payload
    assert "meta" in payload
    assert "graph_of_thought" in payload["meta"]["graph_modes"]
    assert "tool" in payload["meta"]["node_kinds"]


def test_validate_detects_chain_branching_error() -> None:
    client = TestClient(create_app())
    payload = _sample_graph(mode="chain_of_thought")
    payload["nodes"].append(
        {
            "id": "n3",
            "label": "Branch",
            "kind": "thought",
            "module": "",
            "description": "branch",
            "tools": [],
            "config": {},
            "position": {"x": 220, "y": 140},
        }
    )
    payload["edges"].append(
        {
            "id": "e2",
            "source": "n1",
            "target": "n3",
            "source_port": "out",
            "target_port": "in",
            "metadata": {},
        }
    )

    response = client.post("/api/validate", json={"payload": payload})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert any(issue["code"] == "cot_branching" for issue in body["issues"])


def test_validate_allows_cycles_in_graph_mode() -> None:
    client = TestClient(create_app())
    payload = _sample_graph(mode="graph_of_thought")
    payload["edges"].append(
        {
            "id": "e2",
            "source": "n2",
            "target": "n1",
            "source_port": "out",
            "target_port": "in",
            "metadata": {},
        }
    )

    response = client.post("/api/validate", json={"payload": payload})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert not any(issue["severity"] == "error" for issue in body["issues"])


def test_export_json_migrates_v1_payload() -> None:
    client = TestClient(create_app())
    v1_payload = {
        "version": 1,
        "nodes": [
            {"id": "a", "label": "A", "x": 10, "y": 10},
            {"id": "b", "label": "B", "x": 120, "y": 10},
        ],
        "edges": [{"id": "ab", "source": "a", "target": "b"}],
    }

    response = client.post("/api/export/json", json={"payload": v1_payload})
    assert response.status_code == 200
    graph = response.json()["graph"]
    assert graph["version"] == 2
    assert graph["graph"]["mode"] == "graph_of_thought"
    assert graph["nodes"][0]["position"]["x"] == 10.0


def test_export_python_contains_agent_and_tool_stubs() -> None:
    client = TestClient(create_app())
    payload = _sample_graph(mode="tree_of_thought")
    payload["nodes"][0]["kind"] = "agent"
    payload["nodes"][0]["tools"] = ["email_summary"]

    response = client.post("/api/export/python", json={"payload": payload})
    assert response.status_code == 200
    scaffold = response.json()["python"]
    assert "build_nested_agent_node" in scaffold
    assert "check_tool_access" in scaffold
    assert "GRAPH_MODE = \"tree_of_thought\"" in scaffold
