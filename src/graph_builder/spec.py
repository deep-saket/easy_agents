"""Graph specification, migration, validation, and scaffold generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


GRAPH_MODES: tuple[str, ...] = (
    "chain_of_thought",
    "tree_of_thought",
    "graph_of_thought",
)

NODE_KINDS: tuple[str, ...] = (
    "thought",
    "decision",
    "tool",
    "agent",
    "memory",
    "reflect",
    "respond",
    "router",
    "custom",
)


class GraphNode(BaseModel):
    """Represents one node in graph-spec v2."""

    id: str
    label: str
    kind: str = "custom"
    module: str = ""
    description: str = ""
    tools: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] = Field(default_factory=lambda: {"x": 40.0, "y": 40.0})

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in NODE_KINDS:
            return normalized
        return "custom"


class GraphEdge(BaseModel):
    """Represents one directed edge in graph-spec v2."""

    id: str
    source: str
    target: str
    source_port: str = "out"
    target_port: str = "in"
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphSpec(BaseModel):
    """Represents graph-spec v2."""

    version: Literal[2] = 2
    graph: dict[str, Any] = Field(default_factory=lambda: {"mode": "graph_of_thought", "name": "Agent Graph"})
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    @field_validator("graph")
    @classmethod
    def _normalize_graph_meta(cls, value: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(value)
        mode = str(normalized.get("mode", "graph_of_thought")).strip().lower()
        if mode not in GRAPH_MODES:
            mode = "graph_of_thought"
        normalized["mode"] = mode
        normalized.setdefault("name", "Agent Graph")
        return normalized


class ValidationIssue(BaseModel):
    """Validation issue emitted for graph checks."""

    severity: Literal["error", "warning"]
    code: str
    message: str
    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class _GraphIndex:
    node_ids: set[str]
    in_edges: dict[str, list[GraphEdge]]
    out_edges: dict[str, list[GraphEdge]]


def migrate_graph_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Migrates graph payloads to spec v2 shape."""
    version = int(payload.get("version", 1) or 1)
    if version >= 2 and "graph" in payload:
        return payload

    migrated_nodes: list[dict[str, Any]] = []
    for raw in payload.get("nodes", []):
        if not isinstance(raw, dict):
            continue
        migrated_nodes.append(
            {
                "id": str(raw.get("id", "")),
                "label": str(raw.get("label", "Node")),
                "kind": _infer_kind(raw),
                "module": str(raw.get("module", "")),
                "description": str(raw.get("description", "")),
                "tools": list(raw.get("tools", [])) if isinstance(raw.get("tools"), list) else [],
                "config": dict(raw.get("config", {})) if isinstance(raw.get("config"), dict) else {},
                "position": {
                    "x": float(raw.get("x", 40) or 40),
                    "y": float(raw.get("y", 40) or 40),
                },
            }
        )

    migrated_edges: list[dict[str, Any]] = []
    for raw in payload.get("edges", []):
        if not isinstance(raw, dict):
            continue
        migrated_edges.append(
            {
                "id": str(raw.get("id", "")),
                "source": str(raw.get("source", "")),
                "target": str(raw.get("target", "")),
                "source_port": str(raw.get("source_port", "out")),
                "target_port": str(raw.get("target_port", "in")),
                "metadata": dict(raw.get("metadata", {})) if isinstance(raw.get("metadata"), dict) else {},
            }
        )

    graph_meta = payload.get("graph", {}) if isinstance(payload.get("graph"), dict) else {}
    mode = str(graph_meta.get("mode", "graph_of_thought")).strip().lower()
    if mode not in GRAPH_MODES:
        mode = "graph_of_thought"

    return {
        "version": 2,
        "graph": {
            "mode": mode,
            "name": str(graph_meta.get("name", "Agent Graph")),
        },
        "nodes": migrated_nodes,
        "edges": migrated_edges,
    }


def normalize_graph_payload(payload: dict[str, Any]) -> GraphSpec:
    """Migrates and normalizes graph payload into typed v2 model."""
    migrated = migrate_graph_payload(payload)
    return GraphSpec.model_validate(migrated)


def validate_graph_spec(spec: GraphSpec) -> list[ValidationIssue]:
    """Validates graph structure according to selected thought mode."""
    issues: list[ValidationIssue] = []
    index = _build_index(spec)
    issues.extend(_validate_reference_integrity(spec, index))

    mode = str(spec.graph.get("mode", "graph_of_thought"))
    if mode == "chain_of_thought":
        issues.extend(_validate_chain(spec, index))
    elif mode == "tree_of_thought":
        issues.extend(_validate_tree(spec, index))
    else:
        issues.extend(_validate_graph(spec, index))

    return issues


def generate_python_scaffold(spec: GraphSpec) -> str:
    """Generates a runnable scaffold for the normalized graph spec."""
    mode = str(spec.graph.get("mode", "graph_of_thought"))
    node_defs = "\n".join(f"    \"{node.id}\": \"{node.kind}\"," for node in spec.nodes) or "    # Add nodes"
    edge_defs = "\n".join(
        f"    (\"{edge.source}\", \"{edge.target}\", {{\"source_port\": \"{edge.source_port}\", \"target_port\": \"{edge.target_port}\"}}),"
        for edge in spec.edges
    ) or "    # Add edges"
    tools_lookup = {
        node.id: node.tools
        for node in spec.nodes
        if node.tools
    }
    tool_map_literal = repr(tools_lookup) if tools_lookup else "{}"

    return f'''"""Auto-generated scaffold from graph builder (v2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.nodes.types import AgentState
from src.nodes.agent_node import AgentNode


GRAPH_MODE = "{mode}"
NODE_TYPES = {{
{node_defs}
}}
EDGES = [
{edge_defs}
]
NODE_TOOLS = {tool_map_literal}


@dataclass(slots=True)
class PlaceholderNode:
    """Replace with concrete node implementations."""

    node_id: str

    def execute(self, state: AgentState) -> dict[str, Any]:
        # TODO: Implement node execution behavior.
        return {{"observation": {{"node": self.node_id, "status": "placeholder"}}}}


def check_tool_access(node_id: str, tool_name: str) -> bool:
    """Stub: enforce per-node tool access before tool execution."""
    allowed_tools = NODE_TOOLS.get(node_id, [])
    return tool_name in allowed_tools


def build_nested_agent_node(delegate_agent: Any, *, node_id: str) -> AgentNode:
    """Stub: configure AgentNode delegation templates as needed."""
    return AgentNode(
        agent=delegate_agent,
        input_template="{{user_input}}",
        session_id_template="{{session_id}}::delegate::{{agent_name}}",
        include_as_observation=True,
        include_as_response=False,
    )


def build_graph() -> Any:
    graph = StateGraph(AgentState)

    # TODO: Replace placeholder instances with your concrete node bindings.
    bound_nodes = {{node_id: PlaceholderNode(node_id=node_id) for node_id in NODE_TYPES}}

    for node_id, node_instance in bound_nodes.items():
        graph.add_node(node_id, node_instance.execute)

    if not NODE_TYPES:
        return graph.compile()

    # Default start node for scaffold. Change as needed.
    first_node = next(iter(NODE_TYPES.keys()))
    graph.add_edge(START, first_node)

    for source, target, _metadata in EDGES:
        graph.add_edge(source, target)

    # Keep an explicit terminal edge in the scaffold for quick bring-up.
    graph.add_edge(first_node, END)

    return graph.compile()


def run_once(user_input: str, session_id: str = "builder-session") -> dict[str, Any]:
    app = build_graph()
    return app.invoke({{"session_id": session_id, "user_input": user_input, "steps": 0}})
'''


def _infer_kind(raw: dict[str, Any]) -> str:
    value = str(raw.get("kind", "")).strip().lower()
    if value in NODE_KINDS:
        return value
    module = str(raw.get("module", "")).lower()
    label = str(raw.get("label", "")).lower()
    text = f"{module} {label}"
    if "agent" in text:
        return "agent"
    if "tool" in text:
        return "tool"
    if "memory" in text:
        return "memory"
    if "reflect" in text:
        return "reflect"
    if "respond" in text:
        return "respond"
    if "router" in text:
        return "router"
    return "custom"


def _build_index(spec: GraphSpec) -> _GraphIndex:
    node_ids = {node.id for node in spec.nodes}
    in_edges = {node_id: [] for node_id in node_ids}
    out_edges = {node_id: [] for node_id in node_ids}
    for edge in spec.edges:
        if edge.target in in_edges:
            in_edges[edge.target].append(edge)
        if edge.source in out_edges:
            out_edges[edge.source].append(edge)
    return _GraphIndex(node_ids=node_ids, in_edges=in_edges, out_edges=out_edges)


def _validate_reference_integrity(spec: GraphSpec, index: _GraphIndex) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not spec.nodes:
        issues.append(
            ValidationIssue(
                severity="warning",
                code="empty_graph",
                message="Graph has no nodes.",
            )
        )
        return issues

    for edge in spec.edges:
        if edge.source not in index.node_ids or edge.target not in index.node_ids:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_edge_reference",
                    message=f"Edge `{edge.id}` references unknown nodes.",
                    edge_ids=[edge.id],
                )
            )
    return issues


def _validate_chain(spec: GraphSpec, index: _GraphIndex) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not spec.nodes:
        return issues

    roots = [node_id for node_id in index.node_ids if len(index.in_edges[node_id]) == 0]
    leaves = [node_id for node_id in index.node_ids if len(index.out_edges[node_id]) == 0]

    if len(roots) != 1:
        issues.append(
            ValidationIssue(
                severity="error",
                code="cot_root_count",
                message="Chain of thought requires exactly one entry node.",
                node_ids=roots,
            )
        )
    if len(leaves) != 1:
        issues.append(
            ValidationIssue(
                severity="error",
                code="cot_leaf_count",
                message="Chain of thought requires exactly one terminal node.",
                node_ids=leaves,
            )
        )

    for node_id in index.node_ids:
        in_degree = len(index.in_edges[node_id])
        out_degree = len(index.out_edges[node_id])
        if in_degree > 1 or out_degree > 1:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="cot_branching",
                    message="Chain of thought does not allow branching.",
                    node_ids=[node_id],
                    edge_ids=[edge.id for edge in index.in_edges[node_id] + index.out_edges[node_id]],
                )
            )

    cycle_edges = _cycle_edge_ids(spec)
    if cycle_edges:
        issues.append(
            ValidationIssue(
                severity="error",
                code="cot_cycle",
                message="Chain of thought cannot contain cycles.",
                edge_ids=cycle_edges,
            )
        )
    return issues


def _validate_tree(spec: GraphSpec, index: _GraphIndex) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not spec.nodes:
        return issues

    roots = [node_id for node_id in index.node_ids if len(index.in_edges[node_id]) == 0]
    if len(roots) != 1:
        issues.append(
            ValidationIssue(
                severity="error",
                code="tot_root_count",
                message="Tree of thought requires exactly one root node.",
                node_ids=roots,
            )
        )

    for node_id in index.node_ids:
        in_degree = len(index.in_edges[node_id])
        if in_degree > 1:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="tot_parent_count",
                    message="Tree of thought nodes can have at most one parent.",
                    node_ids=[node_id],
                    edge_ids=[edge.id for edge in index.in_edges[node_id]],
                )
            )

    cycle_edges = _cycle_edge_ids(spec)
    if cycle_edges:
        issues.append(
            ValidationIssue(
                severity="error",
                code="tot_cycle",
                message="Tree of thought cannot contain cycles.",
                edge_ids=cycle_edges,
            )
        )
    return issues


def _validate_graph(spec: GraphSpec, index: _GraphIndex) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not spec.nodes:
        return issues

    connected = _connected_node_ids(spec)
    disconnected = sorted(index.node_ids - connected)
    if disconnected:
        issues.append(
            ValidationIssue(
                severity="warning",
                code="got_disconnected_nodes",
                message="Graph contains disconnected nodes.",
                node_ids=disconnected,
            )
        )
    return issues


def _connected_node_ids(spec: GraphSpec) -> set[str]:
    if not spec.nodes:
        return set()
    adjacency: dict[str, set[str]] = {node.id: set() for node in spec.nodes}
    for edge in spec.edges:
        adjacency.setdefault(edge.source, set()).add(edge.target)
        adjacency.setdefault(edge.target, set()).add(edge.source)

    start = spec.nodes[0].id
    seen: set[str] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, set()) - seen)
    return seen


def _cycle_edge_ids(spec: GraphSpec) -> list[str]:
    adjacency: dict[str, list[GraphEdge]] = {}
    for edge in spec.edges:
        adjacency.setdefault(edge.source, []).append(edge)

    visited: set[str] = set()
    in_stack: set[str] = set()
    cycle_edges: set[str] = set()

    def dfs(node_id: str) -> None:
        visited.add(node_id)
        in_stack.add(node_id)
        for edge in adjacency.get(node_id, []):
            target = edge.target
            if target not in visited:
                dfs(target)
            elif target in in_stack:
                cycle_edges.add(edge.id)
        in_stack.remove(node_id)

    for node in spec.nodes:
        if node.id not in visited:
            dfs(node.id)
    return sorted(cycle_edges)
