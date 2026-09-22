const SVG_NS = "http://www.w3.org/2000/svg";

const KIND_ORDER = [
  "specialist",
  "guild",
  "capability",
  "tool",
  "memory",
  "playbook",
  "policy",
  "model",
  "service",
];

const KIND_LABELS = {
  specialist: "Specialists",
  guild: "Circles",
  capability: "Capabilities",
  tool: "Tools",
  memory: "Memory",
  playbook: "Playbooks",
  policy: "Policies",
  model: "Models",
  service: "Services",
};

const KIND_COLORS = {
  specialist: "#b99cff",
  guild: "#ffb866",
  capability: "#52c7e8",
  tool: "#78df91",
  memory: "#f1d06f",
  playbook: "#f28ec7",
  policy: "#ff818f",
  model: "#77a8ff",
  service: "#d0e2e8",
};

const KIND_GLYPHS = {
  specialist: "S",
  guild: "◌",
  capability: "C",
  tool: "T",
  memory: "M",
  playbook: "P",
  policy: "!",
  model: "AI",
  service: "◆",
};

const PRESETS = {
  overview: new Set(["specialist", "guild", "tool", "memory", "playbook", "policy", "model", "service"]),
  agents: new Set(["specialist", "guild"]),
  components: new Set(["guild", "capability", "tool", "memory", "playbook", "policy", "model", "service"]),
  full: new Set(KIND_ORDER),
};

const PLANNED_STATUSES = new Set(["planned", "proposed", "dormant", "scaffolded", "sandboxed"]);

const elements = {
  graph: document.getElementById("graph"),
  viewport: document.getElementById("viewport"),
  edgeLayer: document.getElementById("edge-layer"),
  edgeLabelLayer: document.getElementById("edge-label-layer"),
  nodeLayer: document.getElementById("node-layer"),
  graphStage: document.getElementById("graph-stage"),
  loading: document.getElementById("graph-loading"),
  empty: document.getElementById("graph-empty"),
  tooltip: document.getElementById("tooltip"),
  search: document.getElementById("search"),
  domainFilter: document.getElementById("domain-filter"),
  typeFilters: document.getElementById("type-filters"),
  toggleTypes: document.getElementById("toggle-types"),
  showActive: document.getElementById("show-active"),
  showPlanned: document.getElementById("show-planned"),
  showEdgeLabels: document.getElementById("show-edge-labels"),
  reduceMotion: document.getElementById("reduce-motion"),
  fitView: document.getElementById("fit-view"),
  zoomIn: document.getElementById("zoom-in"),
  zoomOut: document.getElementById("zoom-out"),
  resetView: document.getElementById("reset-view"),
  statSpecialists: document.getElementById("stat-specialists"),
  statComponents: document.getElementById("stat-components"),
  statRelations: document.getElementById("stat-relations"),
  visibleNodes: document.getElementById("visible-nodes"),
  apiState: document.getElementById("api-state"),
  statusText: document.getElementById("status-text"),
  viewKicker: document.getElementById("view-kicker"),
  viewTitle: document.getElementById("view-title"),
  legend: document.getElementById("legend"),
  inspectorEmpty: document.getElementById("inspector-empty"),
  inspector: document.getElementById("inspector"),
  inspectorKind: document.getElementById("inspector-kind"),
  inspectorStatus: document.getElementById("inspector-status"),
  inspectorTitle: document.getElementById("inspector-title"),
  inspectorId: document.getElementById("inspector-id"),
  inspectorDescription: document.getElementById("inspector-description"),
  inspectorTags: document.getElementById("inspector-tags"),
  relationshipList: document.getElementById("relationship-list"),
  relationshipCount: document.getElementById("relationship-count"),
  metadataSection: document.getElementById("metadata-section"),
  metadataList: document.getElementById("metadata-list"),
  focusNeighbors: document.getElementById("focus-neighbors"),
  releaseNode: document.getElementById("release-node"),
  missionSection: document.getElementById("mission-section"),
  missionInput: document.getElementById("mission-input"),
  runMission: document.getElementById("run-mission"),
  missionResult: document.getElementById("mission-result"),
};

const state = {
  graph: { nodes: [], edges: [], counts: {} },
  nodeById: new Map(),
  enabledKinds: new Set(PRESETS.overview),
  preset: "overview",
  domain: "all",
  query: "",
  focusId: null,
  selectedId: null,
  positions: new Map(),
  visibleNodes: [],
  visibleEdges: [],
  nodeElements: new Map(),
  edgeElements: new Map(),
  edgeLabelElements: new Map(),
  transform: { x: 0, y: 0, k: 1 },
  pan: null,
  drag: null,
  suppressBackgroundClickUntil: 0,
  simulationAlpha: 0,
  animationFrame: null,
  hasFitted: false,
};

function svgElement(name, attributes = {}) {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) {
    element.setAttribute(key, String(value));
  }
  return element;
}

function stableHash(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function truncate(value, limit = 29) {
  return value.length > limit ? `${value.slice(0, limit - 1)}…` : value;
}

function nodeRadius(node) {
  if (node.kind === "guild") return 16;
  if (node.kind === "specialist") return 11;
  if (node.kind === "playbook" || node.kind === "service") return 9;
  return 8;
}

function isPlanned(node) {
  return PLANNED_STATUSES.has(String(node.status).toLowerCase());
}

function statusAllowed(node) {
  if (isPlanned(node)) return elements.showPlanned.checked;
  return elements.showActive.checked;
}

function domainSeeds(domain) {
  if (domain === "all") return new Set(state.graph.nodes.map((node) => node.id));
  const seeds = new Set();
  const guildId = `guild:${domain}`;
  for (const node of state.graph.nodes) {
    if (node.id === guildId || node.group === domain) seeds.add(node.id);
  }
  for (const edge of state.graph.edges) {
    if (edge.kind === "member_of" && edge.target === guildId) seeds.add(edge.source);
  }
  const expanded = new Set(seeds);
  for (const edge of state.graph.edges) {
    if (seeds.has(edge.source)) expanded.add(edge.target);
    if (seeds.has(edge.target)) expanded.add(edge.source);
  }
  return expanded;
}

function neighborhood(nodeId) {
  const related = new Set([nodeId]);
  for (const edge of state.graph.edges) {
    if (edge.source === nodeId) related.add(edge.target);
    if (edge.target === nodeId) related.add(edge.source);
  }
  return related;
}

function applyFilters({ reheat = true } = {}) {
  const domainIds = domainSeeds(state.domain);
  const query = state.query.trim().toLowerCase();
  let nodes = state.graph.nodes.filter(
    (node) => state.enabledKinds.has(node.kind) && statusAllowed(node) && domainIds.has(node.id),
  );

  if (state.focusId) {
    const focused = neighborhood(state.focusId);
    nodes = nodes.filter((node) => focused.has(node.id));
  }

  if (query) {
    const matches = new Set(
      nodes
        .filter((node) => {
          const haystack = [node.label, node.description, node.id, ...(node.tags || [])]
            .join(" ")
            .toLowerCase();
          return haystack.includes(query);
        })
        .map((node) => node.id),
    );
    const expanded = new Set(matches);
    for (const edge of state.graph.edges) {
      if (matches.has(edge.source)) expanded.add(edge.target);
      if (matches.has(edge.target)) expanded.add(edge.source);
    }
    nodes = nodes.filter((node) => expanded.has(node.id));
  }

  const visibleIds = new Set(nodes.map((node) => node.id));
  const edges = state.graph.edges.filter(
    (edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target),
  );
  state.visibleNodes = nodes.map(prepareSimulationNode);
  state.visibleEdges = edges;

  renderGraph();
  elements.visibleNodes.textContent = String(nodes.length);
  elements.empty.classList.toggle("hidden", nodes.length > 0);
  elements.statusText.textContent = `${nodes.length} nodes · ${edges.length} visible relationships`;
  updateViewHeading();
  if (reheat) startSimulation(elements.reduceMotion.checked ? 0.08 : 0.65);
}

function prepareSimulationNode(node) {
  const previous = state.positions.get(node.id);
  if (previous) return Object.assign(node, previous);
  const anchor = anchorFor(node);
  const seed = stableHash(node.id);
  const angle = ((seed % 360) * Math.PI) / 180;
  const distance = 18 + (seed % 76);
  const prepared = Object.assign(node, {
    x: anchor.x + Math.cos(angle) * distance,
    y: anchor.y + Math.sin(angle) * distance,
    vx: 0,
    vy: 0,
    fx: null,
    fy: null,
  });
  state.positions.set(node.id, prepared);
  return prepared;
}

function anchorFor(node) {
  const rect = elements.graph.getBoundingClientRect();
  const width = Math.max(rect.width, 700);
  const height = Math.max(rect.height, 520);
  const guilds = state.graph.nodes.filter((item) => item.kind === "guild");
  const guildIndex = Math.max(0, guilds.findIndex((item) => item.id === `guild:${node.group}`));
  const groupAngle = (guildIndex / Math.max(guilds.length, 1)) * Math.PI * 2 - Math.PI / 2;
  const guildAnchor = {
    x: width / 2 + Math.cos(groupAngle) * Math.min(width, height) * 0.24,
    y: height / 2 + Math.sin(groupAngle) * Math.min(width, height) * 0.24,
  };

  if (node.kind === "guild") {
    const index = Math.max(0, guilds.findIndex((item) => item.id === node.id));
    const angle = (index / Math.max(guilds.length, 1)) * Math.PI * 2 - Math.PI / 2;
    return {
      x: width / 2 + Math.cos(angle) * Math.min(width, height) * 0.2,
      y: height / 2 + Math.sin(angle) * Math.min(width, height) * 0.2,
    };
  }
  if (node.kind === "specialist") return guildAnchor;
  if (node.kind === "playbook") return { x: width * 0.5, y: height * 0.14 };
  if (node.kind === "memory") return { x: width * 0.12, y: height * 0.48 };
  if (node.kind === "tool") return { x: width * 0.88, y: height * 0.48 };
  if (node.kind === "policy") return { x: width * 0.18, y: height * 0.82 };
  if (node.kind === "model") return { x: width * 0.82, y: height * 0.15 };
  if (node.kind === "service") return { x: width * 0.5, y: height * 0.5 };
  return { x: width * 0.79, y: height * 0.75 };
}

function renderGraph() {
  elements.edgeLayer.replaceChildren();
  elements.edgeLabelLayer.replaceChildren();
  elements.nodeLayer.replaceChildren();
  state.nodeElements.clear();
  state.edgeElements.clear();
  state.edgeLabelElements.clear();

  for (const edge of state.visibleEdges) {
    const line = svgElement("line", {
      class: `graph-edge${edge.directed ? " directed" : ""}`,
      "data-edge-id": edge.id,
    });
    elements.edgeLayer.append(line);
    state.edgeElements.set(edge.id, line);

    if (elements.showEdgeLabels.checked) {
      const label = svgElement("text", { class: "edge-label" });
      label.textContent = edge.label;
      elements.edgeLabelLayer.append(label);
      state.edgeLabelElements.set(edge.id, label);
    }
  }

  for (const node of state.visibleNodes) {
    const radius = nodeRadius(node);
    const group = svgElement("g", {
      class: `graph-node kind-${node.kind}${isPlanned(node) ? " planned" : ""}`,
      role: "button",
      tabindex: "0",
      "aria-label": `${node.label}, ${KIND_LABELS[node.kind] || node.kind}`,
      "data-node-id": node.id,
    });
    const halo = svgElement("circle", { class: "node-halo", r: radius + 6 });
    const core = svgElement("circle", { class: "node-core", r: radius });
    const glyph = svgElement("text", { class: "node-glyph", x: 0, y: 0 });
    glyph.textContent = KIND_GLYPHS[node.kind] || "•";
    const label = svgElement("text", {
      class: "node-label",
      x: radius + 5,
      y: 3,
    });
    label.textContent = truncate(node.label);
    group.append(halo, core, glyph, label);
    group.addEventListener("pointerdown", (event) => beginNodeDrag(event, node));
    group.addEventListener("click", (event) => {
      event.stopPropagation();
      selectNode(node.id);
    });
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectNode(node.id);
      }
    });
    group.addEventListener("pointerenter", (event) => showTooltip(event, node));
    group.addEventListener("pointermove", moveTooltip);
    group.addEventListener("pointerleave", hideTooltip);
    elements.nodeLayer.append(group);
    state.nodeElements.set(node.id, group);
  }

  applyHighlights();
  updateGraphElements();
}

function applyHighlights() {
  const highlight = state.selectedId ? neighborhood(state.selectedId) : null;
  const query = state.query.trim().toLowerCase();
  for (const node of state.visibleNodes) {
    const element = state.nodeElements.get(node.id);
    if (!element) continue;
    const haystack = [node.label, node.id, ...(node.tags || [])].join(" ").toLowerCase();
    element.classList.toggle("selected", node.id === state.selectedId);
    element.classList.toggle("dimmed", Boolean(highlight && !highlight.has(node.id)));
    element.classList.toggle("search-hit", Boolean(query && haystack.includes(query)));
  }
  for (const edge of state.visibleEdges) {
    const element = state.edgeElements.get(edge.id);
    if (!element) continue;
    const connected = edge.source === state.selectedId || edge.target === state.selectedId;
    element.classList.toggle("emphasis", connected);
    element.classList.toggle("dimmed", Boolean(state.selectedId && !connected));
  }
}

function updateGraphElements() {
  const visibleById = new Map(state.visibleNodes.map((node) => [node.id, node]));
  for (const node of state.visibleNodes) {
    const element = state.nodeElements.get(node.id);
    if (element) element.setAttribute("transform", `translate(${node.x},${node.y})`);
  }
  for (const edge of state.visibleEdges) {
    const source = visibleById.get(edge.source);
    const target = visibleById.get(edge.target);
    const element = state.edgeElements.get(edge.id);
    if (!source || !target || !element) continue;
    element.setAttribute("x1", source.x);
    element.setAttribute("y1", source.y);
    element.setAttribute("x2", target.x);
    element.setAttribute("y2", target.y);
    const label = state.edgeLabelElements.get(edge.id);
    if (label) {
      label.setAttribute("x", (source.x + target.x) / 2);
      label.setAttribute("y", (source.y + target.y) / 2 - 3);
    }
  }
}

function startSimulation(alpha = 0.55) {
  state.simulationAlpha = Math.max(state.simulationAlpha, alpha);
  if (!state.animationFrame) state.animationFrame = requestAnimationFrame(simulationTick);
}

function simulationTick() {
  state.animationFrame = null;
  const nodes = state.visibleNodes;
  if (!nodes.length) return;
  const alpha = state.simulationAlpha;
  const nodeById = new Map(nodes.map((node) => [node.id, node]));

  for (let i = 0; i < nodes.length; i += 1) {
    const left = nodes[i];
    for (let j = i + 1; j < nodes.length; j += 1) {
      const right = nodes[j];
      let dx = right.x - left.x;
      let dy = right.y - left.y;
      let distanceSquared = dx * dx + dy * dy;
      if (distanceSquared < 1) {
        dx = ((stableHash(`${left.id}:${right.id}`) % 10) - 5) / 10;
        dy = 0.5;
        distanceSquared = dx * dx + dy * dy;
      }
      const distance = Math.sqrt(distanceSquared);
      const minimum = nodeRadius(left) + nodeRadius(right) + 13;
      const repulsion = (850 * alpha) / Math.max(distanceSquared, 80);
      const nx = dx / distance;
      const ny = dy / distance;
      left.vx -= nx * repulsion;
      left.vy -= ny * repulsion;
      right.vx += nx * repulsion;
      right.vy += ny * repulsion;
      if (distance < minimum) {
        const collision = ((minimum - distance) / minimum) * 0.22 * alpha;
        left.vx -= nx * collision;
        left.vy -= ny * collision;
        right.vx += nx * collision;
        right.vy += ny * collision;
      }
    }
  }

  for (const edge of state.visibleEdges) {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    if (!source || !target) continue;
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const distance = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
    const desired = edge.kind === "member_of" ? 82 : edge.kind === "has_capability" ? 96 : 116;
    const spring = (distance - desired) * 0.0022 * alpha;
    const nx = dx / distance;
    const ny = dy / distance;
    source.vx += nx * spring;
    source.vy += ny * spring;
    target.vx -= nx * spring;
    target.vy -= ny * spring;
  }

  for (const node of nodes) {
    if (node.fx !== null && node.fy !== null) {
      node.x = node.fx;
      node.y = node.fy;
      node.vx = 0;
      node.vy = 0;
      continue;
    }
    const anchor = anchorFor(node);
    node.vx += (anchor.x - node.x) * 0.00055 * alpha;
    node.vy += (anchor.y - node.y) * 0.00055 * alpha;
    node.vx *= 0.86;
    node.vy *= 0.86;
    node.x += node.vx;
    node.y += node.vy;
    state.positions.set(node.id, node);
  }

  updateGraphElements();
  state.simulationAlpha *= elements.reduceMotion.checked ? 0.72 : 0.955;
  if (state.simulationAlpha > 0.012 || state.drag) {
    state.animationFrame = requestAnimationFrame(simulationTick);
  }
}

function graphPoint(event) {
  const rect = elements.graph.getBoundingClientRect();
  return {
    x: (event.clientX - rect.left - state.transform.x) / state.transform.k,
    y: (event.clientY - rect.top - state.transform.y) / state.transform.k,
  };
}

function beginNodeDrag(event, node) {
  if (event.button !== 0) return;
  event.stopPropagation();
  const point = graphPoint(event);
  state.drag = { node, pointerId: event.pointerId, dx: node.x - point.x, dy: node.y - point.y };
  node.fx = node.x;
  node.fy = node.y;
  event.currentTarget.classList.add("dragging");
  elements.graph.setPointerCapture(event.pointerId);
  selectNode(node.id);
  startSimulation(0.18);
}

function beginPan(event) {
  if (event.button !== 0 || state.drag) return;
  state.pan = {
    pointerId: event.pointerId,
    clientX: event.clientX,
    clientY: event.clientY,
    x: state.transform.x,
    y: state.transform.y,
  };
  elements.graph.setPointerCapture(event.pointerId);
}

function onPointerMove(event) {
  if (state.drag && state.drag.pointerId === event.pointerId) {
    const point = graphPoint(event);
    state.drag.node.fx = point.x + state.drag.dx;
    state.drag.node.fy = point.y + state.drag.dy;
    state.drag.node.x = state.drag.node.fx;
    state.drag.node.y = state.drag.node.fy;
    updateGraphElements();
    return;
  }
  if (state.pan && state.pan.pointerId === event.pointerId) {
    state.transform.x = state.pan.x + event.clientX - state.pan.clientX;
    state.transform.y = state.pan.y + event.clientY - state.pan.clientY;
    applyTransform();
  }
}

function endPointer(event) {
  if (state.drag && state.drag.pointerId === event.pointerId) {
    const element = state.nodeElements.get(state.drag.node.id);
    if (element) element.classList.remove("dragging");
    state.positions.set(state.drag.node.id, state.drag.node);
    state.drag = null;
    // A force-layout node can move between pointerdown and click. In that case
    // the browser may target the following click at the canvas even though the
    // interaction began on a node. Preserve the selection made on pointerdown.
    state.suppressBackgroundClickUntil = Date.now() + 1000;
  }
  if (state.pan && state.pan.pointerId === event.pointerId) state.pan = null;
}

function applyTransform() {
  elements.viewport.setAttribute(
    "transform",
    `translate(${state.transform.x} ${state.transform.y}) scale(${state.transform.k})`,
  );
}

function zoomAt(factor, clientX = null, clientY = null) {
  const rect = elements.graph.getBoundingClientRect();
  const x = clientX === null ? rect.left + rect.width / 2 : clientX;
  const y = clientY === null ? rect.top + rect.height / 2 : clientY;
  const oldScale = state.transform.k;
  const nextScale = Math.max(0.25, Math.min(2.8, oldScale * factor));
  const localX = x - rect.left;
  const localY = y - rect.top;
  state.transform.x = localX - ((localX - state.transform.x) / oldScale) * nextScale;
  state.transform.y = localY - ((localY - state.transform.y) / oldScale) * nextScale;
  state.transform.k = nextScale;
  applyTransform();
}

function fitView() {
  if (!state.visibleNodes.length) return;
  const rect = elements.graph.getBoundingClientRect();
  const xs = state.visibleNodes.map((node) => node.x);
  const ys = state.visibleNodes.map((node) => node.y);
  const minX = Math.min(...xs) - 80;
  const maxX = Math.max(...xs) + 120;
  const minY = Math.min(...ys) - 80;
  const maxY = Math.max(...ys) + 80;
  const width = Math.max(maxX - minX, 1);
  const height = Math.max(maxY - minY, 1);
  const scale = Math.max(0.25, Math.min(1.45, Math.min(rect.width / width, rect.height / height) * 0.9));
  state.transform.k = scale;
  state.transform.x = (rect.width - width * scale) / 2 - minX * scale;
  state.transform.y = (rect.height - height * scale) / 2 - minY * scale;
  applyTransform();
}

function selectNode(nodeId) {
  const node = state.nodeById.get(nodeId);
  if (!node) return;
  state.selectedId = nodeId;
  renderInspector(node);
  applyHighlights();
}

function renderInspector(node) {
  elements.inspectorEmpty.classList.add("hidden");
  elements.inspector.classList.remove("hidden");
  elements.inspectorKind.textContent = KIND_LABELS[node.kind] || node.kind;
  elements.inspectorKind.style.color = KIND_COLORS[node.kind] || "#ffffff";
  elements.inspectorStatus.textContent = node.status;
  elements.inspectorStatus.style.color = isPlanned(node) ? "#ffb866" : "#6ee7d2";
  elements.inspectorTitle.textContent = node.label;
  elements.inspectorId.textContent = node.id;
  elements.inspectorDescription.textContent = node.description || "No description recorded.";
  elements.focusNeighbors.textContent = state.focusId === node.id ? "Show full graph" : "Focus relationships";
  elements.missionSection.classList.toggle("hidden", node.kind !== "specialist");
  elements.missionInput.value = "";
  elements.missionResult.replaceChildren();
  elements.missionResult.classList.add("hidden");

  elements.inspectorTags.replaceChildren();
  for (const tag of node.tags || []) {
    const element = document.createElement("span");
    element.className = "tag";
    element.textContent = tag;
    elements.inspectorTags.append(element);
  }
  if (!(node.tags || []).length) {
    const element = document.createElement("span");
    element.className = "tag";
    element.textContent = "no tags";
    elements.inspectorTags.append(element);
  }

  const relationships = state.graph.edges
    .filter((edge) => edge.source === node.id || edge.target === node.id)
    .map((edge) => ({
      edge,
      outgoing: edge.source === node.id,
      other: state.nodeById.get(edge.source === node.id ? edge.target : edge.source),
    }))
    .filter((item) => item.other)
    .sort((left, right) => left.other.label.localeCompare(right.other.label));
  elements.relationshipCount.textContent = String(relationships.length);
  elements.relationshipList.replaceChildren();
  for (const item of relationships) {
    const button = document.createElement("button");
    button.className = "relationship";
    button.type = "button";
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = item.other.label;
    const relation = document.createElement("span");
    relation.textContent = item.edge.label;
    const direction = document.createElement("span");
    direction.className = "direction";
    direction.textContent = item.outgoing ? "→" : "←";
    copy.append(title, relation);
    button.append(copy, direction);
    button.addEventListener("click", () => revealAndSelect(item.other.id));
    elements.relationshipList.append(button);
  }

  const metadata = {
    group: node.group,
    risk: node.risk,
    ...(node.metadata || {}),
  };
  const entries = Object.entries(metadata).filter(([, value]) => value !== null && value !== undefined && value !== "");
  elements.metadataSection.classList.toggle("hidden", entries.length === 0);
  elements.metadataList.replaceChildren();
  for (const [key, value] of entries) {
    const term = document.createElement("dt");
    const definition = document.createElement("dd");
    term.textContent = key.replaceAll("_", " ");
    definition.textContent = typeof value === "object" ? JSON.stringify(value) : String(value);
    elements.metadataList.append(term, definition);
  }
}

function revealAndSelect(nodeId) {
  const node = state.nodeById.get(nodeId);
  if (!node) return;
  state.enabledKinds.add(node.kind);
  if (!statusAllowed(node)) {
    if (isPlanned(node)) elements.showPlanned.checked = true;
    else elements.showActive.checked = true;
  }
  state.focusId = null;
  renderTypeFilters();
  applyFilters();
  selectNode(nodeId);
  window.setTimeout(() => fitView(), 80);
}

async function runSandboxMission() {
  const node = state.nodeById.get(state.selectedId);
  const objective = elements.missionInput.value.trim();
  if (!node || node.kind !== "specialist") return;
  if (objective.length < 3) {
    renderMissionResult("Input needed", "Describe a bounded task in at least three characters.", []);
    return;
  }
  const originalLabel = elements.runMission.textContent;
  elements.runMission.disabled = true;
  elements.runMission.textContent = "Planning…";
  try {
    const response = await fetch("/api/missions/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        objective,
        specialist_id: node.id.replace(/^specialist:/, ""),
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `Mission request failed (${response.status}).`);
    const result = payload.results?.[0];
    renderMissionResult(
      payload.status || "planned",
      result?.response || payload.synthesis || "No result returned.",
      payload.warnings || [],
    );
  } catch (error) {
    renderMissionResult("Failed", error instanceof Error ? error.message : String(error), []);
  } finally {
    elements.runMission.disabled = false;
    elements.runMission.textContent = originalLabel;
  }
}

function renderMissionResult(status, response, warnings) {
  elements.missionResult.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = status.replaceAll("_", " ");
  const copy = document.createElement("p");
  copy.textContent = response;
  elements.missionResult.append(heading, copy);
  for (const warning of warnings) {
    const note = document.createElement("small");
    note.textContent = warning;
    elements.missionResult.append(note);
  }
  elements.missionResult.classList.remove("hidden");
}

function showTooltip(event, node) {
  elements.tooltip.replaceChildren();
  const title = document.createElement("strong");
  const meta = document.createElement("span");
  title.textContent = node.label;
  meta.textContent = `${KIND_LABELS[node.kind] || node.kind} · ${node.status}`;
  elements.tooltip.append(title, meta);
  elements.tooltip.classList.remove("hidden");
  moveTooltip(event);
}

function moveTooltip(event) {
  elements.tooltip.style.left = `${event.clientX + 13}px`;
  elements.tooltip.style.top = `${event.clientY + 13}px`;
}

function hideTooltip() {
  elements.tooltip.classList.add("hidden");
}

function renderTypeFilters() {
  elements.typeFilters.replaceChildren();
  for (const kind of KIND_ORDER) {
    if (!state.graph.counts[kind]) continue;
    const label = document.createElement("label");
    label.className = `type-filter${state.enabledKinds.has(kind) ? "" : " off"}`;
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = state.enabledKinds.has(kind);
    const dot = document.createElement("span");
    dot.className = "type-dot";
    dot.style.color = KIND_COLORS[kind];
    dot.style.background = KIND_COLORS[kind];
    const text = document.createElement("span");
    text.textContent = `${KIND_LABELS[kind]} · ${state.graph.counts[kind]}`;
    input.addEventListener("change", () => {
      if (input.checked) state.enabledKinds.add(kind);
      else state.enabledKinds.delete(kind);
      state.preset = "custom";
      document.querySelectorAll(".preset").forEach((button) => button.classList.remove("active"));
      renderTypeFilters();
      applyFilters();
    });
    label.append(input, dot, text);
    elements.typeFilters.append(label);
  }
}

function renderLegend() {
  elements.legend.replaceChildren();
  for (const kind of KIND_ORDER) {
    if (!state.graph.counts[kind]) continue;
    const item = document.createElement("span");
    item.className = "legend-item";
    item.style.color = KIND_COLORS[kind];
    const dot = document.createElement("i");
    dot.className = "legend-dot";
    const label = document.createElement("span");
    label.textContent = kind === "guild" ? "circle" : kind;
    item.append(dot, label);
    elements.legend.append(item);
  }
}

function populateDomains() {
  const guilds = state.graph.nodes
    .filter((node) => node.kind === "guild")
    .sort((left, right) => left.label.localeCompare(right.label));
  for (const guild of guilds) {
    const option = document.createElement("option");
    option.value = guild.id.replace(/^guild:/, "");
    option.textContent = guild.label;
    elements.domainFilter.append(option);
  }
}

function updateViewHeading() {
  const domainNode = state.nodeById.get(`guild:${state.domain}`);
  elements.viewKicker.textContent = state.focusId
    ? "Focused neighborhood"
    : domainNode
      ? domainNode.label
      : "All circles";
  const titles = {
    overview: "Your personal agent system",
    agents: "Specialists and their circles",
    components: "Reusable platform components",
    full: "Complete knowledge graph",
    custom: "Custom constellation view",
  };
  elements.viewTitle.textContent = state.focusId
    ? state.nodeById.get(state.focusId)?.label || "Focused relationships"
    : titles[state.preset] || titles.custom;
}

function setPreset(name) {
  state.preset = name;
  state.enabledKinds = new Set(PRESETS[name]);
  state.focusId = null;
  document.querySelectorAll(".preset").forEach((button) => {
    button.classList.toggle("active", button.dataset.preset === name);
  });
  renderTypeFilters();
  applyFilters();
  window.setTimeout(() => fitView(), 90);
}

function bindEvents() {
  document.querySelectorAll(".preset").forEach((button) => {
    button.addEventListener("click", () => setPreset(button.dataset.preset));
  });
  elements.search.addEventListener("input", () => {
    state.query = elements.search.value;
    applyFilters();
  });
  elements.domainFilter.addEventListener("change", () => {
    state.domain = elements.domainFilter.value;
    state.focusId = null;
    applyFilters();
    window.setTimeout(() => fitView(), 100);
  });
  elements.showActive.addEventListener("change", () => applyFilters());
  elements.showPlanned.addEventListener("change", () => applyFilters());
  elements.showEdgeLabels.addEventListener("change", () => renderGraph());
  elements.reduceMotion.addEventListener("change", () => startSimulation(0.08));
  elements.toggleTypes.addEventListener("click", () => {
    const allEnabled = KIND_ORDER.filter((kind) => state.graph.counts[kind]).every((kind) => state.enabledKinds.has(kind));
    state.enabledKinds = allEnabled ? new Set() : new Set(KIND_ORDER);
    state.preset = "custom";
    renderTypeFilters();
    applyFilters();
  });

  elements.graph.addEventListener("pointerdown", (event) => {
    if (event.target.closest?.(".graph-node")) return;
    beginPan(event);
  });
  elements.graph.addEventListener("pointermove", onPointerMove);
  elements.graph.addEventListener("pointerup", endPointer);
  elements.graph.addEventListener("pointercancel", endPointer);
  elements.graph.addEventListener("click", (event) => {
    if (event.target.closest?.(".graph-node")) return;
    if (Date.now() < state.suppressBackgroundClickUntil) {
      state.suppressBackgroundClickUntil = 0;
      return;
    }
    state.selectedId = null;
    state.focusId = null;
    elements.inspector.classList.add("hidden");
    elements.inspectorEmpty.classList.remove("hidden");
    applyHighlights();
  });
  elements.graph.addEventListener("wheel", (event) => {
    event.preventDefault();
    zoomAt(event.deltaY < 0 ? 1.12 : 0.89, event.clientX, event.clientY);
  }, { passive: false });

  elements.zoomIn.addEventListener("click", () => zoomAt(1.2));
  elements.zoomOut.addEventListener("click", () => zoomAt(0.82));
  elements.resetView.addEventListener("click", () => {
    state.transform = { x: 0, y: 0, k: 1 };
    applyTransform();
  });
  elements.fitView.addEventListener("click", fitView);
  elements.focusNeighbors.addEventListener("click", () => {
    if (!state.selectedId) return;
    state.focusId = state.focusId === state.selectedId ? null : state.selectedId;
    applyFilters();
    renderInspector(state.nodeById.get(state.selectedId));
    window.setTimeout(() => fitView(), 80);
  });
  elements.releaseNode.addEventListener("click", () => {
    const position = state.positions.get(state.selectedId);
    if (!position) return;
    position.fx = null;
    position.fy = null;
    startSimulation(0.28);
  });
  elements.runMission.addEventListener("click", runSandboxMission);

  window.addEventListener("resize", () => {
    startSimulation(0.15);
    window.setTimeout(() => fitView(), 100);
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "/" && document.activeElement !== elements.search) {
      event.preventDefault();
      elements.search.focus();
    }
    if (event.key === "Escape") {
      elements.search.value = "";
      state.query = "";
      state.focusId = null;
      applyFilters();
    }
  });
}

async function initialize() {
  bindEvents();
  try {
    const response = await fetch("/api/knowledge-graph");
    if (!response.ok) throw new Error(`Graph API returned ${response.status}`);
    const graph = await response.json();
    state.graph = graph;
    state.nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
    elements.statSpecialists.textContent = String(graph.counts.specialist || 0);
    const componentCount = graph.nodes.length - (graph.counts.specialist || 0) - (graph.counts.guild || 0);
    elements.statComponents.textContent = String(componentCount);
    elements.statRelations.textContent = String(graph.edges.length);
    elements.apiState.textContent = "Local graph ready";
    elements.apiState.className = "health-pill ok";
    elements.loading.classList.add("hidden");
    populateDomains();
    renderTypeFilters();
    renderLegend();
    applyFilters();
    window.setTimeout(() => {
      fitView();
      state.hasFitted = true;
    }, 850);
  } catch (error) {
    elements.loading.classList.remove("hidden");
    elements.loading.querySelector(".loader")?.remove();
    elements.loading.querySelector("strong").textContent = "Could not load the constellation";
    elements.loading.querySelector("span").textContent = error.message;
    elements.apiState.textContent = "API unavailable";
    elements.apiState.className = "health-pill error";
    elements.statusText.textContent = error.message;
  }
}

initialize();
