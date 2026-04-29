const nodePalette = document.getElementById("node-palette");
const agentPalette = document.getElementById("agent-palette");
const nodeLayer = document.getElementById("node-layer");
const edgeLayer = document.getElementById("edge-layer");
const statusEl = document.getElementById("status");
const validationEl = document.getElementById("validation-status");
const issueListEl = document.getElementById("issue-list");
const graphModeEl = document.getElementById("graph-mode");
const edgeStyleEl = document.getElementById("edge-style");
const connectModeBtn = document.getElementById("connect-mode");
const deleteLoopsBtn = document.getElementById("delete-loops");
const fitBtn = document.getElementById("fit-view");
const clearBtn = document.getElementById("clear-graph");
const exportRuntimeBtn = document.getElementById("export-runtime");
const importJsonBtn = document.getElementById("import-json");
const exportSvgBtn = document.getElementById("export-svg");
const exportPngBtn = document.getElementById("export-png");
const includeDescriptionExportEl = document.getElementById("include-description-export");
const importFileInput = document.getElementById("import-file");

const inspectorEmptyEl = document.getElementById("inspector-empty");
const nodeInspectorEl = document.getElementById("node-inspector");
const nodeLabelEl = document.getElementById("node-label");
const nodeKindEl = document.getElementById("node-kind");
const nodeDescriptionEl = document.getElementById("node-description");
const nodeToolsEl = document.getElementById("node-tools");
const nodeConfigEl = document.getElementById("node-config");
const configErrorEl = document.getElementById("config-error");
const edgeInspectorEmptyEl = document.getElementById("edge-inspector-empty");
const edgeInspectorEl = document.getElementById("edge-inspector");
const edgeIdEl = document.getElementById("edge-id");
const edgeStepsEl = document.getElementById("edge-steps");
const deleteEdgeBtn = document.getElementById("delete-edge");
const LOCAL_STORAGE_KEY = "easy_agents_graph_builder_v2";

const state = {
  nodes: [],
  edges: [],
  selection: null,
  drag: null,
  edgeDraft: null,
  connectSourceId: null,
  connectMode: false,
  lastDragEndedAt: 0,
  mode: "graph_of_thought",
  edgeStyle: "square",
  issues: [],
  lastValidationTimer: null,
  meta: {
    graph_modes: ["chain_of_thought", "tree_of_thought", "graph_of_thought"],
    node_kinds: ["custom"],
    default_configs: {},
  },
};

function setStatus(text) {
  statusEl.textContent = text;
}

function uid(prefix) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function defaultConfigForKind(kind) {
  const defaults = state.meta.default_configs || {};
  if (defaults[kind]) {
    return JSON.parse(JSON.stringify(defaults[kind]));
  }
  return {};
}

function getNodeById(nodeId) {
  return state.nodes.find((node) => node.id === nodeId);
}

function getEdgeById(edgeId) {
  return state.edges.find((edge) => edge.id === edgeId);
}

function getNodeCenter(node) {
  return { x: node.position.x + node.width / 2, y: node.position.y + node.height / 2 };
}

function normalizePort(port, fallback = "right") {
  const value = String(port || "").toLowerCase();
  if (value === "in" || value === "left") return "left";
  if (value === "out" || value === "right") return "right";
  if (value === "top") return "top";
  if (value === "bottom") return "bottom";
  return fallback;
}

function getHandlePoint(node, port) {
  const resolved = normalizePort(port);
  if (resolved === "left") {
    return { x: node.position.x - 1, y: node.position.y + node.height / 2 };
  }
  if (resolved === "top") {
    return { x: node.position.x + node.width / 2, y: node.position.y - 1 };
  }
  if (resolved === "bottom") {
    return { x: node.position.x + node.width / 2, y: node.position.y + node.height + 1 };
  }
  return { x: node.position.x + node.width + 1, y: node.position.y + node.height / 2 };
}

function buildPayload() {
  return {
    version: 2,
    graph: {
      mode: state.mode,
      name: "Agent Graph",
      edge_style: state.edgeStyle,
    },
    nodes: state.nodes.map((node) => ({
      id: node.id,
      label: node.label,
      kind: node.kind,
      module: node.module,
      description: node.description,
      tools: [...node.tools],
      config: JSON.parse(JSON.stringify(node.config)),
      position: {
        x: node.position.x,
        y: node.position.y,
      },
    })),
    edges: state.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      source_port: edge.source_port,
      target_port: edge.target_port,
      metadata: JSON.parse(JSON.stringify(edge.metadata)),
    })),
  };
}

function normalizeStepsText(raw) {
  const text = String(raw || "").trim();
  if (!text) return "";
  const chunks = text.split(",").map((chunk) => chunk.trim()).filter(Boolean);
  const out = [];
  for (const chunk of chunks) {
    const match = /^([LRUD])\s*(-?\d+)$/i.exec(chunk);
    if (!match) {
      throw new Error(`Invalid step '${chunk}'. Use L/R/U/D with pixels, e.g. L8,U4,R5.`);
    }
    out.push(`${match[1].toUpperCase()}${Number(match[2])}`);
  }
  return out.join(",");
}

function migrateSnapshot(snapshot) {
  if (snapshot && Number(snapshot.version || 0) >= 2 && snapshot.graph) {
    return snapshot;
  }

  const nodes = Array.isArray(snapshot?.nodes)
    ? snapshot.nodes.map((raw) => {
        const kind = String(raw.kind || "custom").toLowerCase();
        const normalizedKind = (state.meta.node_kinds || []).includes(kind) ? kind : "custom";
        return {
          id: String(raw.id || uid("node")),
          label: String(raw.label || "Node"),
          kind: normalizedKind,
          module: String(raw.module || ""),
          description: String(raw.description || ""),
          tools: Array.isArray(raw.tools) ? raw.tools.map((item) => String(item)) : [],
          config: raw.config && typeof raw.config === "object" ? raw.config : defaultConfigForKind(normalizedKind),
          position: {
            x: Number(raw.position?.x ?? raw.x ?? 40),
            y: Number(raw.position?.y ?? raw.y ?? 40),
          },
        };
      })
    : [];

  const validNodeIds = new Set(nodes.map((node) => node.id));
  const edges = Array.isArray(snapshot?.edges)
    ? snapshot.edges
        .map((raw) => ({
          id: String(raw.id || uid("edge")),
          source: String(raw.source || ""),
          target: String(raw.target || ""),
          source_port: normalizePort(String(raw.source_port || "right"), "right"),
          target_port: normalizePort(String(raw.target_port || "left"), "left"),
          metadata: raw.metadata && typeof raw.metadata === "object" ? raw.metadata : {},
        }))
        .filter((edge) => validNodeIds.has(edge.source) && validNodeIds.has(edge.target))
    : [];

  return {
    version: 2,
    graph: {
      mode: String(snapshot?.graph?.mode || "graph_of_thought"),
      name: String(snapshot?.graph?.name || "Agent Graph"),
    },
    nodes,
    edges,
  };
}

function loadPayload(payload) {
  const migrated = migrateSnapshot(payload);
  state.mode = (state.meta.graph_modes || []).includes(migrated.graph.mode) ? migrated.graph.mode : "graph_of_thought";
  state.edgeStyle = String(migrated.graph?.edge_style || "square").toLowerCase() === "straight" ? "straight" : "square";

  state.nodes = migrated.nodes.map((node) => ({
    id: node.id,
    label: node.label,
    kind: node.kind,
    module: node.module || "",
    description: node.description || "",
    tools: Array.isArray(node.tools) ? [...node.tools] : [],
    config: node.config && typeof node.config === "object" ? JSON.parse(JSON.stringify(node.config)) : defaultConfigForKind(node.kind),
    position: {
      x: Number(node.position?.x || 40),
      y: Number(node.position?.y || 40),
    },
    width: 210,
    height: 92,
  }));

  const validNodeIds = new Set(state.nodes.map((node) => node.id));
  state.edges = migrated.edges
    .filter((edge) => validNodeIds.has(edge.source) && validNodeIds.has(edge.target))
    .map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      source_port: normalizePort(edge.source_port || "right", "right"),
      target_port: normalizePort(edge.target_port || "left", "left"),
      metadata: edge.metadata && typeof edge.metadata === "object" ? edge.metadata : {},
    }));

  state.selection = null;
  graphModeEl.value = state.mode;
  if (edgeStyleEl) {
    edgeStyleEl.value = state.edgeStyle;
  }
  render();
  scheduleValidation();
  persistGraph();
}

function updateSelection(nextSelection) {
  state.selection = nextSelection;
  render();
}

function setConnectMode(enabled) {
  state.connectMode = enabled;
  if (!enabled) {
    state.connectSourceId = null;
  }
  document.body.classList.toggle("connect-mode", enabled);
  if (connectModeBtn) {
    connectModeBtn.classList.toggle("active", enabled);
    connectModeBtn.textContent = `Edge Tool: ${enabled ? "On" : "Off"}`;
  }
}

function persistGraph() {
  try {
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(buildPayload()));
  } catch (_error) {
    // Ignore local persistence failures.
  }
}

function restorePersistedGraph() {
  try {
    const raw = localStorage.getItem(LOCAL_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return null;
    }
    return parsed;
  } catch (_error) {
    return null;
  }
}

function addNode(item) {
  const kind = String(item.kind || "custom").toLowerCase();
  const normalizedKind = (state.meta.node_kinds || []).includes(kind) ? kind : "custom";
  const node = {
    id: uid("node"),
    label: item.label || "Node",
    kind: normalizedKind,
    module: item.module || "",
    description: "",
    tools: [],
    config: defaultConfigForKind(normalizedKind),
    position: {
      x: 80 + state.nodes.length * 22,
      y: 60 + state.nodes.length * 18,
    },
    width: 210,
    height: 92,
  };

  state.nodes.push(node);
  setStatus(`Added ${node.label}`);
  render();
  scheduleValidation();
  persistGraph();
}

function tryAddEdge(sourceNodeId, targetNodeId, sourcePort = "right", targetPort = "left") {
  if (!sourceNodeId || !targetNodeId) {
    setStatus("Connection requires source and target nodes.");
    return false;
  }
  if (sourceNodeId === targetNodeId) {
    setStatus("Cannot connect a node to itself.");
    return false;
  }
  const exists = state.edges.some((edge) => edge.source === sourceNodeId && edge.target === targetNodeId);
  if (exists) {
    setStatus("Edge already exists.");
    return false;
  }
  state.edges.push({
    id: uid("edge"),
    source: sourceNodeId,
    target: targetNodeId,
    source_port: normalizePort(sourcePort, "right"),
    target_port: normalizePort(targetPort, "left"),
    metadata: {},
  });
  setStatus(`Edge created (${sourceNodeId} -> ${targetNodeId}).`);
  return true;
}

function removeSelection() {
  if (!state.selection) return;

  if (state.selection.type === "node") {
    state.nodes = state.nodes.filter((node) => node.id !== state.selection.id);
    state.edges = state.edges.filter((edge) => edge.source !== state.selection.id && edge.target !== state.selection.id);
    setStatus("Node removed.");
  }

  if (state.selection.type === "edge") {
    state.edges = state.edges.filter((edge) => edge.id !== state.selection.id);
    setStatus("Edge removed.");
  }

  state.selection = null;
  render();
  scheduleValidation();
  persistGraph();
}

function beginNodeDrag(node, event) {
  state.drag = {
    nodeId: node.id,
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    baseX: node.position.x,
    baseY: node.position.y,
  };
}

function updateNodeDrag(event) {
  if (!state.drag) return;
  const node = getNodeById(state.drag.nodeId);
  if (!node) return;

  const dx = event.clientX - state.drag.startX;
  const dy = event.clientY - state.drag.startY;
  node.position.x = state.drag.baseX + dx;
  node.position.y = state.drag.baseY + dy;
  render();
}

function endNodeDrag() {
  if (!state.drag) return;
  state.drag = null;
  state.lastDragEndedAt = Date.now();
  scheduleValidation();
  persistGraph();
}

function beginEdgeDraft(sourceNodeId, event) {
  const sourceNode = getNodeById(sourceNodeId);
  if (!sourceNode) return;
  const wrapRect = nodeLayer.getBoundingClientRect();
  const sourcePort = normalizePort(event?.target?.dataset?.port || "right", "right");
  const from = event?.target?.dataset?.port
    ? getHandlePoint(sourceNode, sourcePort)
    : getNodeCenter(sourceNode);
  state.edgeDraft = {
    sourceNodeId,
    sourcePort,
    from,
    to: {
      x: event.clientX - wrapRect.left,
      y: event.clientY - wrapRect.top,
    },
  };
  render();
}

function updateEdgeDraft(event) {
  if (!state.edgeDraft) return;
  const wrapRect = nodeLayer.getBoundingClientRect();
  state.edgeDraft.to = {
    x: event.clientX - wrapRect.left,
    y: event.clientY - wrapRect.top,
  };
  renderEdges();
}

function completeEdgeDraft(targetNodeId, targetPort = "left") {
  if (!state.edgeDraft) return;

  const sourceNodeId = state.edgeDraft.sourceNodeId;
  tryAddEdge(sourceNodeId, targetNodeId, state.edgeDraft.sourcePort || "right", targetPort);
  state.edgeDraft = null;
  state.connectSourceId = null;
  render();
  scheduleValidation();
  persistGraph();
}

function cancelEdgeDraft() {
  if (!state.edgeDraft) return;
  state.edgeDraft = null;
  render();
}

function edgeClasses(edge, issueEdgeIds) {
  const classes = ["edge"];
  if (state.selection?.type === "edge" && state.selection.id === edge.id) {
    classes.push("selected");
  }
  if (issueEdgeIds.has(edge.id)) {
    classes.push("error");
  }
  return classes.join(" ");
}

function applyManualSteps(from, to, stepsText) {
  const parts = [`M ${from.x} ${from.y}`];
  let x = from.x;
  let y = from.y;
  for (const chunk of String(stepsText || "").split(",").map((item) => item.trim()).filter(Boolean)) {
    const match = /^([LRUD])(-?\d+)$/i.exec(chunk);
    if (!match) continue;
    const direction = match[1].toUpperCase();
    const amount = Number(match[2]);
    if (direction === "L") x -= amount;
    if (direction === "R") x += amount;
    if (direction === "U") y -= amount;
    if (direction === "D") y += amount;
    parts.push(`L ${x} ${y}`);
  }
  parts.push(`L ${to.x} ${to.y}`);
  return parts.join(" ");
}

function buildSelfLoopPath(node, sourcePort, targetPort) {
  const s = getHandlePoint(node, sourcePort);
  const t = getHandlePoint(node, targetPort);
  const pad = 32;
  const x0 = node.position.x;
  const y0 = node.position.y;
  const x1 = node.position.x + node.width;
  const y1 = node.position.y + node.height;

  if (sourcePort === "top" || targetPort === "top") {
    return `M ${s.x} ${s.y} L ${s.x} ${y0 - pad} L ${t.x} ${y0 - pad} L ${t.x} ${t.y}`;
  }
  if (sourcePort === "bottom" || targetPort === "bottom") {
    return `M ${s.x} ${s.y} L ${s.x} ${y1 + pad} L ${t.x} ${y1 + pad} L ${t.x} ${t.y}`;
  }
  if (sourcePort === "left" || targetPort === "left") {
    return `M ${s.x} ${s.y} L ${x0 - pad} ${s.y} L ${x0 - pad} ${t.y} L ${t.x} ${t.y}`;
  }
  return `M ${s.x} ${s.y} L ${x1 + pad} ${s.y} L ${x1 + pad} ${t.y} L ${t.x} ${t.y}`;
}

function buildStraightPath(from, to) {
  return `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
}

function buildSquarePath(from, to, sourcePort, targetPort) {
  const sx = from.x;
  const sy = from.y;
  const tx = to.x;
  const ty = to.y;

  if (sourcePort === "left" || sourcePort === "right") {
    const midX = sx + (tx - sx) / 2;
    return `M ${sx} ${sy} L ${midX} ${sy} L ${midX} ${ty} L ${tx} ${ty}`;
  }
  const midY = sy + (ty - sy) / 2;
  return `M ${sx} ${sy} L ${sx} ${midY} L ${tx} ${midY} L ${tx} ${ty}`;
}

function buildEdgePath({ edge, sourceNode, targetNode, sourcePort, targetPort, style }) {
  if (sourceNode.id === targetNode.id) {
    return buildSelfLoopPath(sourceNode, sourcePort, targetPort);
  }
  const from = getHandlePoint(sourceNode, sourcePort);
  const to = getHandlePoint(targetNode, targetPort);
  const manual = String(edge?.metadata?.route_steps || "").trim();
  if (manual) {
    return applyManualSteps(from, to, manual);
  }
  if (style === "straight") {
    return buildStraightPath(from, to);
  }
  return buildSquarePath(from, to, sourcePort, targetPort);
}

function renderEdges() {
  const wrapRect = nodeLayer.getBoundingClientRect();
  edgeLayer.setAttribute("width", String(Math.max(1, Math.round(wrapRect.width))));
  edgeLayer.setAttribute("height", String(Math.max(1, Math.round(wrapRect.height))));
  edgeLayer.setAttribute("viewBox", `0 0 ${Math.max(1, Math.round(wrapRect.width))} ${Math.max(1, Math.round(wrapRect.height))}`);
  edgeLayer.innerHTML = `
    <defs>
      <marker id="arrowhead" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
        <polygon points="0 0, 8 3, 0 6" fill="#2f61a7"></polygon>
      </marker>
    </defs>
  `;

  const issueEdgeIds = new Set(state.issues.flatMap((issue) => issue.edge_ids || []));

  for (const edge of state.edges) {
    const source = getNodeById(edge.source);
    const target = getNodeById(edge.target);
    if (!source || !target) continue;
    const sourcePort = normalizePort(edge.source_port || "right", "right");
    const targetPort = normalizePort(edge.target_port || "left", "left");
    const path = buildEdgePath({
      edge,
      sourceNode: source,
      targetNode: target,
      sourcePort,
      targetPort,
      style: state.edgeStyle,
    });
    const pathEl = document.createElementNS("http://www.w3.org/2000/svg", "path");
    pathEl.setAttribute("d", path);
    pathEl.setAttribute("class", edgeClasses(edge, issueEdgeIds));
    pathEl.style.pointerEvents = "stroke";
    pathEl.addEventListener("click", (event) => {
      event.stopPropagation();
      updateSelection({ type: "edge", id: edge.id });
    });
    edgeLayer.appendChild(pathEl);
  }

  if (state.edgeDraft) {
    const preview = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const draftPath = state.edgeStyle === "straight"
      ? buildStraightPath(state.edgeDraft.from, state.edgeDraft.to)
      : buildSquarePath(
          state.edgeDraft.from,
          state.edgeDraft.to,
          normalizePort(state.edgeDraft.sourcePort || "right", "right"),
          "left"
        );
    preview.setAttribute("d", draftPath);
    preview.setAttribute("class", "preview-edge");
    edgeLayer.appendChild(preview);
  }
}

function nodeClasses(node, issueNodeIds) {
  const classes = ["node"];
  if (state.selection?.type === "node" && state.selection.id === node.id) {
    classes.push("selected");
  }
  if (issueNodeIds.has(node.id)) {
    classes.push("error");
  }
  return classes.join(" ");
}

function buildNodeElement(node, issueNodeIds) {
  const element = document.createElement("div");
  element.className = nodeClasses(node, issueNodeIds);
  element.style.left = `${node.position.x}px`;
  element.style.top = `${node.position.y}px`;
  element.innerHTML = `
    <div class="title">${escapeHtml(node.label)}</div>
    <div class="meta">${escapeHtml(node.kind)}</div>
    <div class="description">${escapeHtml(node.description || "")}</div>
    <div class="handle handle-top" data-role="port" data-port="top" title="Top port"></div>
    <div class="handle handle-right" data-role="port" data-port="right" title="Right port"></div>
    <div class="handle handle-bottom" data-role="port" data-port="bottom" title="Bottom port"></div>
    <div class="handle handle-left" data-role="port" data-port="left" title="Left port"></div>
  `;

  element.addEventListener("pointerdown", (event) => {
    const hasPort = Boolean(event.target?.dataset?.port);
    if (state.connectMode && !hasPort && (event.shiftKey || event.altKey)) {
      event.stopPropagation();
      beginEdgeDraft(node.id, event);
      setStatus(`Dragging edge from ${node.label}. Release on target node. (Shift/Alt drag mode)`);
      return;
    }
    if (hasPort) {
      return;
    }
    element.setPointerCapture(event.pointerId);
    beginNodeDrag(node, event);
  });

  element.addEventListener("pointermove", (event) => {
    if (state.drag?.nodeId === node.id) {
      updateNodeDrag(event);
    }
  });

  element.addEventListener("pointerup", (event) => {
    if (state.edgeDraft) {
      event.stopPropagation();
      completeEdgeDraft(node.id);
      return;
    }
    if (state.drag?.nodeId === node.id) {
      endNodeDrag();
    }
  });

  element.addEventListener("click", (event) => {
    if (Date.now() - state.lastDragEndedAt < 180) {
      return;
    }
    const hasPort = Boolean(event.target?.dataset?.port);
    if (hasPort) {
      return;
    }
    event.stopPropagation();
    if (state.connectMode) {
      if (!state.connectSourceId) {
        state.connectSourceId = `${node.id}::right`;
        setStatus(`Source selected: ${node.label}. Click target node.`);
      } else {
        const [sourceNodeId, sourcePort = "right"] = String(state.connectSourceId).split("::");
        const connected = tryAddEdge(sourceNodeId, node.id, sourcePort, "left");
        state.connectSourceId = null;
        if (connected) {
          render();
          scheduleValidation();
          persistGraph();
        }
      }
      return;
    }
    if (state.connectSourceId) {
      const [sourceNodeId, sourcePort = "right"] = String(state.connectSourceId).split("::");
      const connected = tryAddEdge(sourceNodeId, node.id, sourcePort, "left");
      state.connectSourceId = null;
      if (connected) {
        render();
        scheduleValidation();
        persistGraph();
      }
      return;
    }
    updateSelection({ type: "node", id: node.id });
  });

  const handles = Array.from(element.querySelectorAll(".handle"));
  for (const handle of handles) {
    handle.addEventListener("pointerdown", (event) => {
      event.stopPropagation();
      beginEdgeDraft(node.id, event);
      const port = normalizePort(event.currentTarget?.dataset?.port || "right", "right");
      setStatus(`Dragging edge from ${node.label} (${port}). Release on target node.`);
    });
    handle.addEventListener("pointerup", (event) => {
      event.stopPropagation();
      const targetPort = normalizePort(event.currentTarget?.dataset?.port || "left", "left");
      completeEdgeDraft(node.id, targetPort);
    });
    handle.addEventListener("click", (event) => {
      event.stopPropagation();
      const port = normalizePort(event.currentTarget?.dataset?.port || "right", "right");
      if (!state.connectSourceId) {
        state.connectSourceId = `${node.id}::${port}`;
        setStatus(`Source selected: ${node.label} (${port}). Click target node or target port.`);
        return;
      }
      const [sourceNodeId, sourcePort = "right"] = String(state.connectSourceId).split("::");
      const connected = tryAddEdge(sourceNodeId, node.id, sourcePort, port);
      state.connectSourceId = null;
      if (connected) {
        render();
        scheduleValidation();
        persistGraph();
      }
    });
  }

  return element;
}

function renderNodes() {
  nodeLayer.innerHTML = "";
  const issueNodeIds = new Set(state.issues.flatMap((issue) => issue.node_ids || []));
  for (const node of state.nodes) {
    nodeLayer.appendChild(buildNodeElement(node, issueNodeIds));
  }
}

function renderValidation() {
  const errorCount = state.issues.filter((issue) => issue.severity === "error").length;
  const warningCount = state.issues.filter((issue) => issue.severity === "warning").length;
  validationEl.classList.remove("ok", "error");

  if (errorCount > 0) {
    validationEl.classList.add("error");
    validationEl.textContent = `${errorCount} error(s), ${warningCount} warning(s)`;
  } else {
    validationEl.classList.add("ok");
    validationEl.textContent = warningCount > 0 ? `${warningCount} warning(s)` : "No validation issues.";
  }

  issueListEl.innerHTML = "";
  if (state.issues.length === 0) {
    issueListEl.innerHTML = '<div class="muted">No issues.</div>';
    return;
  }

  for (const issue of state.issues) {
    const div = document.createElement("div");
    div.className = `issue-item ${issue.severity}`;
    div.innerHTML = `
      <div class="code">${escapeHtml(issue.code)}</div>
      <div>${escapeHtml(issue.message)}</div>
    `;
    issueListEl.appendChild(div);
  }
}

function renderInspector() {
  if (!state.selection || state.selection.type !== "node") {
    nodeInspectorEl.classList.add("hidden");
    inspectorEmptyEl.classList.remove("hidden");
    return;
  }

  const node = getNodeById(state.selection.id);
  if (!node) {
    nodeInspectorEl.classList.add("hidden");
    inspectorEmptyEl.classList.remove("hidden");
    return;
  }

  inspectorEmptyEl.classList.add("hidden");
  nodeInspectorEl.classList.remove("hidden");

  nodeLabelEl.value = node.label;
  nodeKindEl.value = node.kind;
  nodeDescriptionEl.value = node.description || "";
  nodeToolsEl.value = node.tools.join(",");
  nodeConfigEl.value = JSON.stringify(node.config || {}, null, 2);
  configErrorEl.classList.add("hidden");
  configErrorEl.textContent = "";
}

function renderEdgeInspector() {
  if (!state.selection || state.selection.type !== "edge") {
    edgeInspectorEl.classList.add("hidden");
    edgeInspectorEmptyEl.classList.remove("hidden");
    return;
  }
  const edge = getEdgeById(state.selection.id);
  if (!edge) {
    edgeInspectorEl.classList.add("hidden");
    edgeInspectorEmptyEl.classList.remove("hidden");
    return;
  }
  edgeInspectorEmptyEl.classList.add("hidden");
  edgeInspectorEl.classList.remove("hidden");
  edgeIdEl.value = edge.id;
  edgeStepsEl.value = String(edge.metadata?.route_steps || "");
}

function render() {
  renderEdges();
  renderNodes();
  renderInspector();
  renderEdgeInspector();
  renderValidation();
}

function downloadFile(name, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

function graphBounds() {
  if (state.nodes.length === 0) {
    return { x: 0, y: 0, width: 800, height: 600 };
  }
  const xs = state.nodes.map((node) => node.position.x);
  const ys = state.nodes.map((node) => node.position.y);
  const xe = state.nodes.map((node) => node.position.x + node.width);
  const ye = state.nodes.map((node) => node.position.y + node.height);
  const pad = 28;
  return {
    x: Math.min(...xs) - pad,
    y: Math.min(...ys) - pad,
    width: Math.max(320, Math.max(...xe) - Math.min(...xs) + pad * 2),
    height: Math.max(240, Math.max(...ye) - Math.min(...ys) + pad * 2),
  };
}

function serializeSvg(includeDescriptions = true) {
  const bounds = graphBounds();
  const shiftedNodes = state.nodes.map((node) => ({
    ...node,
    position: {
      x: node.position.x - bounds.x,
      y: node.position.y - bounds.y,
    },
  }));

  const lineMarkup = state.edges
    .map((edge) => {
      const source = shiftedNodes.find((node) => node.id === edge.source);
      const target = shiftedNodes.find((node) => node.id === edge.target);
      if (!source || !target) return "";
      const sourcePort = normalizePort(edge.source_port || "right", "right");
      const targetPort = normalizePort(edge.target_port || "left", "left");
      const path = buildEdgePath({
        edge,
        sourceNode: source,
        targetNode: target,
        sourcePort,
        targetPort,
        style: state.edgeStyle,
      });
      return `<path d="${path}" stroke="#5678aa" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#arrow)"/>`;
    })
    .join("\n");

  const nodeMarkup = shiftedNodes
    .map((node) => {
      const description = includeDescriptions && node.description
        ? `<text x="${node.position.x + 12}" y="${node.position.y + 66}" font-family="IBM Plex Sans, Segoe UI, sans-serif" font-size="10" fill="#43577a">${escapeHtml(node.description)}</text>`
        : "";
      return `<g>
        <rect x="${node.position.x}" y="${node.position.y}" rx="12" ry="12" width="${node.width}" height="${node.height}" fill="#f7fbff" stroke="#7f9abf"/>
        <text x="${node.position.x + 12}" y="${node.position.y + 26}" font-family="IBM Plex Sans, Segoe UI, sans-serif" font-size="13" font-weight="700" fill="#17212f">${escapeHtml(node.label)}</text>
        <text x="${node.position.x + 12}" y="${node.position.y + 46}" font-family="IBM Plex Sans, Segoe UI, sans-serif" font-size="11" fill="#5a6b84">${escapeHtml(node.kind)}</text>
        ${description}
      </g>`;
    })
    .join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${bounds.width}" height="${bounds.height}" viewBox="0 0 ${bounds.width} ${bounds.height}">
  <defs>
    <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
      <polygon points="0 0, 8 3, 0 6" fill="#5678aa"/>
    </marker>
  </defs>
  <rect width="100%" height="100%" fill="#eef2f8"/>
  ${lineMarkup}
  ${nodeMarkup}
</svg>`;
}

async function exportPng() {
  const svg = serializeSvg(includeDescriptionExportEl.checked);
  const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  try {
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = reject;
      img.src = url;
    });

    const bounds = graphBounds();
    const canvas = document.createElement("canvas");
    canvas.width = bounds.width;
    canvas.height = bounds.height;

    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0);

    const pngBlob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png", 1));
    if (!pngBlob) throw new Error("Could not build PNG.");

    const pngUrl = URL.createObjectURL(pngBlob);
    const link = document.createElement("a");
    link.href = pngUrl;
    link.download = "agent-graph.png";
    link.click();
    URL.revokeObjectURL(pngUrl);
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function runValidation() {
  const response = await fetch("/api/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ payload: buildPayload() }),
  });
  const payload = await response.json();
  state.issues = Array.isArray(payload.issues) ? payload.issues : [];
  renderValidation();
  renderEdges();
  renderNodes();
}

function scheduleValidation() {
  if (state.lastValidationTimer) {
    clearTimeout(state.lastValidationTimer);
  }
  state.lastValidationTimer = setTimeout(() => {
    runValidation().catch((error) => {
      setStatus(`Validation failed: ${error.message}`);
    });
  }, 120);
}

function renderPalette(target, items) {
  target.innerHTML = "";
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item.label;
    button.title = item.description || item.module || item.label;
    button.addEventListener("click", () => addNode(item));
    target.appendChild(button);
  }
}

function populateKinds(kinds) {
  nodeKindEl.innerHTML = "";
  for (const kind of kinds) {
    const option = document.createElement("option");
    option.value = kind;
    option.textContent = kind;
    nodeKindEl.appendChild(option);
  }
}

async function loadCatalog() {
  const response = await fetch("/api/catalog");
  const payload = await response.json();

  state.meta = payload.meta || state.meta;
  renderPalette(nodePalette, payload.nodes || []);
  renderPalette(agentPalette, payload.agents || []);
  populateKinds(state.meta.node_kinds || ["custom"]);

  graphModeEl.innerHTML = "";
  for (const mode of state.meta.graph_modes || ["graph_of_thought"]) {
    const option = document.createElement("option");
    option.value = mode;
    option.textContent = mode;
    graphModeEl.appendChild(option);
  }
  graphModeEl.value = state.mode;
}

fitBtn.addEventListener("click", () => {
  const wrap = document.getElementById("canvas-wrap");
  const bounds = graphBounds();
  const scale = Math.min((wrap.clientWidth - 20) / bounds.width, (wrap.clientHeight - 20) / bounds.height, 1);

  for (const node of state.nodes) {
    node.position.x = 10 + (node.position.x - bounds.x) * scale;
    node.position.y = 10 + (node.position.y - bounds.y) * scale;
  }
  setStatus("View fitted.");
  render();
  scheduleValidation();
});

clearBtn.addEventListener("click", () => {
  state.nodes = [];
  state.edges = [];
  state.selection = null;
  state.issues = [];
  setStatus("Graph cleared.");
  render();
  scheduleValidation();
  persistGraph();
});

graphModeEl.addEventListener("change", () => {
  state.mode = graphModeEl.value;
  setStatus(`Mode set to ${state.mode}.`);
  scheduleValidation();
  persistGraph();
});

if (edgeStyleEl) {
  edgeStyleEl.addEventListener("change", () => {
    state.edgeStyle = edgeStyleEl.value === "straight" ? "straight" : "square";
    setStatus(`Edge style set to ${state.edgeStyle}.`);
    render();
    persistGraph();
  });
}

if (edgeInspectorEl) {
  edgeInspectorEl.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!state.selection || state.selection.type !== "edge") return;
    const edge = getEdgeById(state.selection.id);
    if (!edge) return;
    try {
      const normalized = normalizeStepsText(edgeStepsEl.value);
      edge.metadata = edge.metadata && typeof edge.metadata === "object" ? edge.metadata : {};
      if (normalized) {
        edge.metadata.route_steps = normalized;
      } else {
        delete edge.metadata.route_steps;
      }
      setStatus("Edge route updated.");
      render();
      persistGraph();
    } catch (error) {
      setStatus(error.message);
    }
  });
}

if (deleteEdgeBtn) {
  deleteEdgeBtn.addEventListener("click", () => {
    if (!state.selection || state.selection.type !== "edge") return;
    state.edges = state.edges.filter((edge) => edge.id !== state.selection.id);
    state.selection = null;
    setStatus("Edge deleted.");
    render();
    scheduleValidation();
    persistGraph();
  });
}

if (deleteLoopsBtn) {
  deleteLoopsBtn.addEventListener("click", () => {
    const before = state.edges.length;
    state.edges = state.edges.filter((edge) => edge.source !== edge.target);
    const removed = before - state.edges.length;
    setStatus(removed > 0 ? `Deleted ${removed} loop edge(s).` : "No loop edges found.");
    render();
    scheduleValidation();
    persistGraph();
  });
}

nodeInspectorEl.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!state.selection || state.selection.type !== "node") return;
  const node = getNodeById(state.selection.id);
  if (!node) return;

  let parsedConfig;
  try {
    parsedConfig = JSON.parse(nodeConfigEl.value || "{}");
  } catch (error) {
    configErrorEl.textContent = `Invalid JSON: ${error.message}`;
    configErrorEl.classList.remove("hidden");
    return;
  }

  configErrorEl.classList.add("hidden");
  node.label = nodeLabelEl.value.trim() || node.label;
  node.kind = nodeKindEl.value;
  node.description = nodeDescriptionEl.value.trim();
  node.tools = nodeToolsEl.value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
  node.config = parsedConfig;

  setStatus("Node updated.");
  render();
  scheduleValidation();
  persistGraph();
});

exportRuntimeBtn.addEventListener("click", async () => {
  const payload = buildPayload();

  const [jsonResponse, pythonResponse] = await Promise.all([
    fetch("/api/export/json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload }),
    }),
    fetch("/api/export/python", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload }),
    }),
  ]);

  if (!jsonResponse.ok || !pythonResponse.ok) {
    const errPayload = await (jsonResponse.ok ? pythonResponse : jsonResponse).json();
    setStatus(errPayload?.detail?.message || "Export failed due to validation errors.");
    return;
  }

  const jsonData = await jsonResponse.json();
  const pythonData = await pythonResponse.json();

  downloadFile("agent-graph.json", JSON.stringify(jsonData.graph, null, 2), "application/json");
  downloadFile("agent-graph-scaffold.py", pythonData.python, "text/x-python");

  setStatus("Runtime bundle exported (JSON + Python scaffold).");
});

if (connectModeBtn) {
  connectModeBtn.addEventListener("click", () => {
    const next = !state.connectMode;
    setConnectMode(next);
    setStatus(next ? "Edge tool enabled. Move nodes normally, or click source->target to connect. Shift/Alt-drag also creates edge." : "Edge tool disabled.");
  });
}

importJsonBtn.addEventListener("click", () => {
  importFileInput.value = "";
  importFileInput.click();
});

importFileInput.addEventListener("change", async (event) => {
  const [file] = event.target.files || [];
  if (!file) return;
  const text = await file.text();
  try {
    loadPayload(JSON.parse(text));
    setStatus("Graph imported.");
  } catch (error) {
    setStatus(`Import failed: ${error.message}`);
  }
});

exportSvgBtn.addEventListener("click", () => {
  const svg = serializeSvg(includeDescriptionExportEl.checked);
  downloadFile("agent-graph.svg", svg, "image/svg+xml");
  setStatus("SVG exported.");
});

exportPngBtn.addEventListener("click", async () => {
  try {
    await exportPng();
    setStatus("PNG exported.");
  } catch (error) {
    setStatus(`PNG export failed: ${error.message}`);
  }
});

nodeLayer.addEventListener("pointermove", (event) => {
  if (state.edgeDraft) {
    const rect = nodeLayer.getBoundingClientRect();
    state.edgeDraft.to = {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
    renderEdges();
  }
});

nodeLayer.addEventListener("pointerup", (event) => {
  if (state.edgeDraft) {
    if (event.target !== nodeLayer) {
      return;
    }
    cancelEdgeDraft();
  }
});

edgeLayer.addEventListener("click", () => updateSelection(null));
nodeLayer.addEventListener("click", () => updateSelection(null));

document.addEventListener("pointermove", (event) => {
  if (state.drag) {
    updateNodeDrag(event);
  }
  if (state.edgeDraft) {
    updateEdgeDraft(event);
  }
});

document.addEventListener("pointerup", () => {
  if (state.drag) {
    endNodeDrag();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Delete" || event.key === "Backspace") {
    const activeTag = document.activeElement?.tagName?.toLowerCase();
    if (activeTag === "input" || activeTag === "textarea" || activeTag === "select") return;
    event.preventDefault();
    removeSelection();
  }
});

try {
  await loadCatalog();
} catch (error) {
  setStatus(`Catalog load failed: ${error.message}`);
}

const persisted = restorePersistedGraph();
loadPayload(persisted || { version: 2, graph: { mode: "graph_of_thought", name: "Agent Graph" }, nodes: [], edges: [] });
setConnectMode(false);
setStatus("Ready. Add nodes and connect with Edge Tool.");
scheduleValidation();
