const SVG_NS = "http://www.w3.org/2000/svg";

const KIND_ORDER = [
  "galaxy",
  "rogue_star",
  "constellation",
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
  galaxy: "Galaxies",
  rogue_star: "Rogue Stars",
  constellation: "Constellations",
  specialist: "Rocky Planets",
  guild: "Circles",
  capability: "Capabilities",
  tool: "Satellites",
  memory: "Memory",
  playbook: "Playbooks",
  policy: "Policies",
  model: "Models",
  service: "Services",
};

const LEGEND_LABELS = {
  guild: "circle",
  rogue_star: "rogue star",
  specialist: "rocky planet",
  tool: "satellite",
};

const KIND_COLORS = {
  galaxy: "#6ee7d2",
  rogue_star: "#ffcf5c",
  constellation: "#f7df83",
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
  galaxy: "✹",
  rogue_star: "★",
  constellation: "✶",
  specialist: "R",
  guild: "◌",
  capability: "C",
  tool: "S",
  memory: "M",
  playbook: "P",
  policy: "!",
  model: "AI",
  service: "◆",
};

const PRESETS = {
  overview: new Set(["galaxy", "rogue_star", "constellation", "specialist", "guild", "tool", "memory", "playbook", "policy", "model", "service"]),
  agents: new Set(["galaxy", "rogue_star", "constellation", "specialist", "guild", "service"]),
  components: new Set(["galaxy", "rogue_star", "constellation", "guild", "capability", "tool", "memory", "playbook", "policy", "model", "service"]),
  full: new Set(KIND_ORDER),
};

const PLANNED_STATUSES = new Set(["planned", "proposed", "dormant", "scaffolded", "sandboxed"]);
const TERMINAL_ACTIONS = new Set(["completed", "failed", "blocked", "cancelled", "denied", "rejected"]);
const STREAM_EVENT_TYPES = [
  "mission.created", "wormhole.accepted", "galaxy.entered", "circle.selected", "mission.routed", "mission.started", "mission.completed", "mission.failed", "mission.cancelled",
  "work_order.created", "work_order.queued", "work_order.started", "work_order.completed", "work_order.blocked", "work_order.failed",
  "specialist.selected", "specialist.started", "specialist.completed", "specialist.failed",
  "playbook.started", "playbook.completed", "playbook.failed",
  "step.started", "step.planned", "step.completed", "step.waiting", "step.failed",
  "handoff.requested", "handoff.accepted", "handoff.completed", "handoff.rejected",
  "policy.allowed", "policy.blocked",
  "approval.requested", "approval.approved", "approval.denied", "approval.expired",
  "tool.requested", "tool.started", "tool.completed", "tool.failed",
  "model.requested", "model.started", "model.completed", "model.failed",
  "memory.read", "memory.write", "memory.denied", "memory.deleted",
  "artifact.created", "artifact.updated", "artifact.deleted",
  "node.started", "node.state_changed", "node.completed", "node.failed", "transition.selected",
  "worker.online", "worker.offline", "worker.heartbeat", "resource.sampled", "stream.gap_detected",
  "alert.opened", "alert.acknowledged", "alert.resolved",
  "fleet_validation.started", "fleet_validation.completed", "fleet_validation.agent_failed",
];

const elements = {
  graph: document.getElementById("graph"),
  viewport: document.getElementById("viewport"),
  edgeLayer: document.getElementById("edge-layer"),
  edgeLabelLayer: document.getElementById("edge-label-layer"),
  activityEdgeLayer: document.getElementById("activity-edge-layer"),
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
  statSpecialistsLabel: document.getElementById("stat-specialists-label"),
  statComponents: document.getElementById("stat-components"),
  statComponentsLabel: document.getElementById("stat-components-label"),
  statRelations: document.getElementById("stat-relations"),
  statRelationsLabel: document.getElementById("stat-relations-label"),
  visibleNodes: document.getElementById("visible-nodes"),
  apiState: document.getElementById("api-state"),
  statusText: document.getElementById("status-text"),
  viewKicker: document.getElementById("view-kicker"),
  viewTitle: document.getElementById("view-title"),
  legend: document.getElementById("legend"),
  inspectorEmpty: document.getElementById("inspector-empty"),
  inspector: document.getElementById("inspector"),
  closeInspector: document.getElementById("close-inspector"),
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
  missionModel: document.getElementById("mission-model"),
  missionModelStatus: document.getElementById("mission-model-status"),
  runMission: document.getElementById("run-mission"),
  missionResult: document.getElementById("mission-result"),
  operationsControls: document.getElementById("operations-controls"),
  statusFilter: document.getElementById("status-filter"),
  attentionOnly: document.getElementById("attention-only"),
  followLive: document.getElementById("follow-live"),
  timeline: document.getElementById("timeline"),
  timelineTitle: document.getElementById("timeline-title"),
  timelinePosition: document.getElementById("timeline-position"),
  timelineScrubber: document.getElementById("timeline-scrubber"),
  eventRail: document.getElementById("event-rail"),
  jumpLive: document.getElementById("jump-live"),
  operationsOverview: document.getElementById("operations-overview"),
  operationsSummary: document.getElementById("operations-summary"),
  missionList: document.getElementById("mission-list"),
  missionCount: document.getElementById("mission-count"),
  operationsEventList: document.getElementById("operations-event-list"),
  eventCount: document.getElementById("event-count"),
  activitySection: document.getElementById("activity-section"),
  activityStatus: document.getElementById("activity-status"),
  activityList: document.getElementById("activity-list"),
  streamState: document.getElementById("stream-state"),
  testAllAgents: document.getElementById("test-all-agents"),
  fleetTestResult: document.getElementById("fleet-test-result"),
  entryPanel: document.getElementById("constellation-entry"),
  guidePanel: document.getElementById("guide-panel"),
  entryObjective: document.getElementById("entry-objective"),
  routeEntry: document.getElementById("route-entry"),
  entryResult: document.getElementById("entry-result"),
  chatPanel: document.getElementById("chat-panel"),
  chatTranscript: document.getElementById("chat-transcript"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
  chatSend: document.getElementById("chat-send"),
  newChat: document.getElementById("new-chat"),
  chatModelState: document.getElementById("chat-model-state"),
  chatRuntimeState: document.getElementById("chat-runtime-state"),
  runtimeReadinessStatus: document.getElementById("runtime-readiness-status"),
  runtimePlanetReadiness: document.getElementById("runtime-planet-readiness"),
  runtimeSatelliteReadiness: document.getElementById("runtime-satellite-readiness"),
  runtimeEffectReadiness: document.getElementById("runtime-effect-readiness"),
  chatRouteStatus: document.getElementById("chat-route-status"),
  chatRouteContext: document.getElementById("chat-route-context"),
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
  entryRouting: {
    nodeIds: new Set(),
    edgeKeys: new Set(),
    plan: null,
  },
  chat: {
    conversationId: null,
    sending: false,
    gemmaReady: false,
    readiness: null,
    visualizationRoute: null,
  },
  operations: {
    mode: "map",
    eventSource: null,
    events: [],
    missions: [],
    runs: [],
    entities: new Map(),
    activityEdges: [],
    activityEdgeElements: new Map(),
    lastSequence: 0,
    replayCount: 0,
    replaySequence: 0,
    connection: "offline",
    renderFrame: null,
  },
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

function relationshipKey(left, right) {
  return [left, right].sort().join("|");
}

function nodeRadius(node) {
  if (node.metadata?.entrypoint) return 15;
  if (node.kind === "galaxy") return 23;
  if (node.kind === "rogue_star") return 17;
  if (node.kind === "constellation") return 19;
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

  if (state.entryRouting.nodeIds.size) {
    nodes = nodes.filter((node) => state.entryRouting.nodeIds.has(node.id));
  }

  const visibleIds = new Set(nodes.map((node) => node.id));
  const edges = state.graph.edges.filter(
    (edge) => visibleIds.has(edge.source)
      && visibleIds.has(edge.target)
      && (!edge.metadata?.routing_only
        || state.entryRouting.edgeKeys.has(relationshipKey(edge.source, edge.target)))
      && !(edge.kind === "member_of"
        && state.entryRouting.edgeKeys.has(relationshipKey(edge.source, edge.target))),
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
  if (state.entryRouting.nodeIds.size) {
    const y = height * 0.7;
    if (node.metadata?.entrypoint) return { x: width * 0.08, y };
    if (node.kind === "galaxy") return { x: width * 0.32, y };
    if (node.kind === "guild") return { x: width * 0.62, y };
    if (node.kind === "specialist") return { x: width * 0.88, y };
  }
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
  if (node.kind === "galaxy") return { x: width * 0.5, y: height * 0.42 };
  if (node.kind === "constellation") return { x: width * 0.5, y: height * 0.58 };
  if (node.kind === "specialist") return guildAnchor;
  if (node.kind === "playbook") return { x: width * 0.5, y: height * 0.14 };
  if (node.kind === "memory") return { x: width * 0.12, y: height * 0.48 };
  if (node.kind === "tool") return { x: width * 0.88, y: height * 0.48 };
  if (node.kind === "policy") return { x: width * 0.18, y: height * 0.82 };
  if (node.kind === "model") return { x: width * 0.82, y: height * 0.15 };
  if (node.kind === "rogue_star") return { x: width * 0.9, y: height * 0.18 };
  if (node.metadata?.entrypoint) return { x: width * 0.5, y: height * 0.18 };
  if (node.kind === "service") return { x: width * 0.5, y: height * 0.58 };
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
      class: `graph-node kind-${node.kind}${isPlanned(node) ? " planned" : ""}${node.metadata?.entrypoint ? " entrypoint" : ""}`,
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
  applyOperationalHighlights();
  renderActivityEdges();
  updateGraphElements();
}

function applyHighlights() {
  const highlight = state.selectedId ? neighborhood(state.selectedId) : null;
  const query = state.query.trim().toLowerCase();
  const routed = state.entryRouting.nodeIds.size > 0;
  for (const node of state.visibleNodes) {
    const element = state.nodeElements.get(node.id);
    if (!element) continue;
    const haystack = [node.label, node.id, ...(node.tags || [])].join(" ").toLowerCase();
    const routeHighlight = state.entryRouting.nodeIds.has(node.id);
    element.classList.toggle("selected", node.id === state.selectedId);
    element.classList.toggle("route-highlight", routeHighlight);
    element.classList.toggle(
      "dimmed",
      Boolean((highlight && !highlight.has(node.id)) || (routed && !routeHighlight)),
    );
    element.classList.toggle("search-hit", Boolean(query && haystack.includes(query)));
  }
  for (const edge of state.visibleEdges) {
    const element = state.edgeElements.get(edge.id);
    if (!element) continue;
    const connected = edge.source === state.selectedId || edge.target === state.selectedId;
    const routeHighlight = state.entryRouting.edgeKeys.has(relationshipKey(edge.source, edge.target));
    element.classList.toggle("emphasis", connected);
    element.classList.toggle("route-highlight", routeHighlight);
    element.classList.toggle(
      "dimmed",
      Boolean((state.selectedId && !connected) || (routed && !routeHighlight)),
    );
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
  updateActivityEdgeElements();
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
  if (state.entryRouting.nodeIds.size) {
    const topInset = elements.entryPanel.offsetTop + elements.entryPanel.offsetHeight + 16;
    const availableHeight = Math.max(rect.height - topInset, 100);
    state.transform.y = topInset + (availableHeight - height * scale) / 2 - minY * scale;
  } else {
    state.transform.y = (rect.height - height * scale) / 2 - minY * scale;
  }
  applyTransform();
}

function selectNode(nodeId) {
  const node = state.nodeById.get(nodeId);
  if (!node) return;
  state.selectedId = nodeId;
  document.body.classList.add("inspector-open");
  elements.operationsOverview.classList.add("hidden");
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
  elements.focusNeighbors.textContent = state.focusId === node.id
    ? "Show full graph"
    : node.kind === "specialist" ? "View Solar System" : "Focus relationships";
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
    .filter((edge) => (edge.source === node.id || edge.target === node.id)
      && !(edge.kind === "member_of"
        && state.entryRouting.edgeKeys.has(relationshipKey(edge.source, edge.target))))
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
  renderNodeActivity(node);
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
  elements.runMission.textContent = elements.missionModel.value === "mac_gemma" ? "Gemma is reasoning…" : "Planning…";
  try {
    const response = await fetch("/api/missions/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        objective,
        specialist_id: node.id.replace(/^specialist:/, ""),
        model_id: elements.missionModel.value,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `Mission request failed (${response.status}).`);
    const result = payload.results?.[0];
    renderMissionResult(
      payload.status || "planned",
      result?.response || payload.synthesis || "No result returned.",
      payload.warnings || [],
      result?.used_model || null,
    );
  } catch (error) {
    renderMissionResult("Failed", error instanceof Error ? error.message : String(error), []);
  } finally {
    elements.runMission.disabled = false;
    elements.runMission.textContent = originalLabel;
  }
}

function renderMissionResult(status, response, warnings, usedModel = null) {
  elements.missionResult.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = status.replaceAll("_", " ");
  const copy = document.createElement("p");
  copy.textContent = response;
  elements.missionResult.append(heading, copy);
  if (usedModel) {
    const model = document.createElement("small");
    model.textContent = `Generated by ${usedModel} through the external Mac-serving endpoint.`;
    elements.missionResult.append(model);
  }
  for (const warning of warnings) {
    const note = document.createElement("small");
    note.textContent = warning;
    elements.missionResult.append(note);
  }
  elements.missionResult.classList.remove("hidden");
}

function updateMissionModelControl() {
  const usesGemma = elements.missionModel.value === "mac_gemma";
  elements.runMission.textContent = usesGemma ? "Run with Mac Gemma" : "Build deterministic plan";
}

async function loadGemmaStatus() {
  const gemmaOption = elements.missionModel.querySelector('option[value="mac_gemma"]');
  try {
    const response = await fetch("/api/v2/readiness");
    if (!response.ok) throw new Error(`Runtime readiness returned ${response.status}`);
    const readiness = await response.json();
    const status = readiness.gemma;
    state.chat.readiness = readiness;
    const localSatelliteCount = readiness.satellites?.locally_executable?.length || 0;
    const advisoryPlanets = readiness.planets?.advisory_executable || 0;
    const activePlanets = readiness.planets?.active || 0;
    const historyLabel = readiness.chat?.persistent ? "persistent history" : "session history";
    elements.chatRuntimeState.textContent = `${localSatelliteCount} local Satellites · ${advisoryPlanets} advisory Planets (${activePlanets} active) · ${historyLabel}`;
    elements.chatRuntimeState.className = "chat-runtime-state ready";
    elements.runtimeReadinessStatus.textContent = readiness.status;
    elements.runtimeReadinessStatus.className = readiness.status === "operational" ? "ready" : "unavailable";
    elements.runtimePlanetReadiness.textContent = `${activePlanets} active + ${readiness.planets?.sandboxed || 0} sandboxed = ${advisoryPlanets} advisory-capable Planets.`;
    elements.runtimeSatelliteReadiness.textContent = `${localSatelliteCount} of ${readiness.satellites?.declared || 0} declared Satellites execute locally in Chat.`;
    elements.runtimeEffectReadiness.textContent = `${readiness.planets?.autonomous_effects_enabled || 0} Planets have autonomous external effects; sends, calls, and purchases remain approval-gated.`;
    if (status.ready && (status.models || []).includes("gemma-4-E4B")) {
      state.chat.gemmaReady = true;
      gemmaOption.disabled = false;
      elements.missionModel.value = "mac_gemma";
      elements.missionModelStatus.textContent = "Ready · gemma-4-E4B at 127.0.0.1:8080";
      elements.missionModelStatus.className = "model-readiness ready";
      elements.chatModelState.textContent = "Gemma ready · 127.0.0.1:8080";
      elements.chatModelState.className = "chat-model-state ready";
    } else {
      state.chat.gemmaReady = false;
      gemmaOption.disabled = true;
      elements.missionModel.value = "none";
      elements.missionModelStatus.textContent = "Unavailable · start the external mac-serving service";
      elements.missionModelStatus.className = "model-readiness unavailable";
      elements.chatModelState.textContent = "Gemma unavailable";
      elements.chatModelState.className = "chat-model-state unavailable";
    }
  } catch (error) {
    state.chat.gemmaReady = false;
    gemmaOption.disabled = true;
    elements.missionModel.value = "none";
    elements.missionModelStatus.textContent = "Unavailable · could not check Mac Gemma";
    elements.missionModelStatus.className = "model-readiness unavailable";
    elements.chatModelState.textContent = "Gemma status unavailable";
    elements.chatModelState.className = "chat-model-state unavailable";
    elements.chatRuntimeState.textContent = "Runtime readiness unavailable";
    elements.chatRuntimeState.className = "chat-runtime-state unavailable";
    elements.runtimeReadinessStatus.textContent = "Unavailable";
    elements.runtimeReadinessStatus.className = "unavailable";
    elements.runtimePlanetReadiness.textContent = "Could not verify Planet execution status.";
    elements.runtimeSatelliteReadiness.textContent = "Could not verify Satellite execution status.";
  }
  updateMissionModelControl();
}

function appendChatMessage(role, content, payload = null, extraClass = "") {
  const message = document.createElement("article");
  message.className = `chat-message ${role}${extraClass ? ` ${extraClass}` : ""}`;
  const avatar = document.createElement("span");
  avatar.className = "chat-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = role === "user" ? "U" : "✹";
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  const heading = document.createElement("strong");
  heading.textContent = role === "user" ? "You" : "Personal Agent Galaxy";
  const copy = document.createElement("p");
  copy.textContent = content;
  bubble.append(heading, copy);

  if (payload) {
    const meta = document.createElement("div");
    meta.className = "chat-message-meta";
    const planet = payload.route_context?.planets?.[0];
    for (const label of [
      payload.status,
      planet?.display_name,
      payload.used_model,
      payload.satellite_invocations?.length
        ? `${payload.satellite_invocations.length} Satellite invoked`
        : null,
    ].filter(Boolean)) {
      const chip = document.createElement("span");
      chip.textContent = String(label).replaceAll("_", " ");
      meta.append(chip);
    }
    bubble.append(meta);
    if (payload.visualization_route) {
      const mapButton = document.createElement("button");
      mapButton.type = "button";
      mapButton.className = "chat-map-button";
      mapButton.textContent = "Show this route on the Map";
      mapButton.addEventListener("click", async () => {
        applyEntrypointRoute(payload.visualization_route);
        await setMode("map");
      });
      bubble.append(mapButton);
    }
  }
  message.append(avatar, bubble);
  elements.chatTranscript.append(message);
  elements.chatTranscript.scrollTop = elements.chatTranscript.scrollHeight;
  return message;
}

function chatRouteStep(glyph, label, detail, kind = "") {
  const step = document.createElement("div");
  step.className = `chat-route-step${kind ? ` ${kind}` : ""}`;
  const icon = document.createElement("span");
  icon.className = "chat-route-glyph";
  icon.textContent = glyph;
  const copy = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = label;
  const caption = document.createElement("small");
  caption.textContent = detail;
  copy.append(title, caption);
  step.append(icon, copy);
  return step;
}

function chatRouteGroup(label) {
  const group = document.createElement("section");
  group.className = "chat-route-group";
  const heading = document.createElement("span");
  heading.textContent = label;
  group.append(heading);
  return group;
}

function satelliteResultSummary(invocation) {
  const output = invocation.output || {};
  if (invocation.satellite?.id === "calculate") {
    return `${output.expression} = ${output.result}`;
  }
  if (invocation.satellite?.id === "unit_convert") {
    return `${output.original_value} ${output.from_unit} = ${output.converted_value} ${output.to_unit}`;
  }
  if (invocation.satellite?.id === "memory_write") {
    return `Stored: ${output.item?.content_text || "validated memory record"}`;
  }
  if (invocation.satellite?.id === "memory_search") {
    return `${output.total || 0} matching memory record(s)`;
  }
  return "Validated tool output returned";
}

function renderChatRoute(payload) {
  const context = payload.route_context;
  elements.chatRouteContext.replaceChildren();
  elements.chatRouteStatus.textContent = String(payload.status || "completed").replaceAll("_", " ");

  const direct = chatRouteGroup("Direct Mission route");
  direct.append(chatRouteStep("◎", "Wormhole", "Controlled Galaxy ingress"));
  direct.append(chatRouteStep("✹", context.galaxy.display_name, "Galaxy ownership boundary"));
  for (const circle of context.circles || []) {
    direct.append(chatRouteStep("◌", circle.display_name, "Selected Circle"));
  }
  for (const planet of context.planets || []) {
    direct.append(chatRouteStep("R", planet.display_name, "Accountable routed Planet"));
  }
  elements.chatRouteContext.append(direct);

  if (context.constellations?.length) {
    const overlays = chatRouteGroup("Constellation context · not a route hop");
    for (const constellation of context.constellations) {
      overlays.append(chatRouteStep("✶", constellation.display_name, "Connected operational overlay", "constellation"));
    }
    elements.chatRouteContext.append(overlays);
  }

  const tools = chatRouteGroup("Available Satellites");
  if (context.available_satellites?.length) {
    const chips = document.createElement("div");
    chips.className = "chat-route-chips";
    for (const satellite of context.available_satellites) {
      const chip = document.createElement("span");
      const invoked = context.invoked_satellites?.some((item) => item.id === satellite.id);
      chip.className = `chat-route-chip${satellite.status === "executable" ? " executable" : ""}${invoked ? " invoked" : ""}`;
      const readiness = satellite.status === "executable" ? "ready" : satellite.status;
      chip.textContent = `${satellite.display_name}${readiness ? ` · ${readiness}` : ""}`;
      chips.append(chip);
    }
    tools.append(chips);
    const invocation = document.createElement("p");
    invocation.className = "entry-error";
    invocation.textContent = context.invoked_satellites?.length
      ? `${context.invoked_satellites.length} Satellite(s) invoked for this answer.`
      : "No Satellite was invoked; the Planet answered with model reasoning only.";
    tools.append(invocation);
  } else {
    const empty = document.createElement("p");
    empty.className = "entry-error";
    empty.textContent = "The selected Planet declares no callable Satellite for this Mission.";
    tools.append(empty);
  }
  elements.chatRouteContext.append(tools);

  if (payload.satellite_invocations?.length) {
    const executed = chatRouteGroup("Invoked Satellite results");
    for (const invocation of payload.satellite_invocations) {
      executed.append(
        chatRouteStep(
          "S",
          invocation.satellite.display_name,
          satelliteResultSummary(invocation),
          "satellite",
        ),
      );
    }
    elements.chatRouteContext.append(executed);
  }

  if (context.rogue_stars?.length) {
    const external = chatRouteGroup("External reasoning resource");
    for (const star of context.rogue_stars) {
      external.append(chatRouteStep("★", star.display_name, "Rogue Star · external local model", "rogue-star"));
    }
    elements.chatRouteContext.append(external);
  }
}

async function submitChat(event) {
  event?.preventDefault();
  const message = elements.chatInput.value.trim();
  if (state.chat.sending || message.length < 3) return;
  appendChatMessage("user", message);
  elements.chatInput.value = "";
  const pending = appendChatMessage("assistant", "Routing through the Wormhole and waiting for the selected Planet…", null, "pending");
  state.chat.sending = true;
  elements.chatSend.disabled = true;
  elements.chatSend.textContent = "Galaxy is thinking…";
  try {
    const body = { message };
    if (state.chat.conversationId) body.conversation_id = state.chat.conversationId;
    const response = await fetch("/api/v2/wormhole/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `Wormhole chat returned ${response.status}.`);
    state.chat.conversationId = payload.conversation_id;
    state.chat.visualizationRoute = payload.visualization_route;
    pending.remove();
    appendChatMessage(
      "assistant",
      payload.answer,
      payload,
      payload.status === "completed" ? "" : "error",
    );
    renderChatRoute(payload);
    elements.statusText.textContent = `Mission ${shortId(payload.mission_id)} · ${payload.route_context.planets?.[0]?.display_name || "Planet"}`;
  } catch (error) {
    pending.remove();
    appendChatMessage(
      "assistant",
      error instanceof Error ? error.message : String(error),
      null,
      "error",
    );
    elements.chatRouteStatus.textContent = "Failed";
  } finally {
    state.chat.sending = false;
    elements.chatSend.disabled = false;
    elements.chatSend.textContent = "Send through Wormhole";
    elements.chatInput.focus();
  }
}

async function resetChat() {
  const conversationId = state.chat.conversationId;
  let deletionError = null;
  if (conversationId) {
    try {
      const response = await fetch(
        `/api/v2/wormhole/conversations/${encodeURIComponent(conversationId)}`,
        { method: "DELETE" },
      );
      if (!response.ok) throw new Error(`Conversation delete returned ${response.status}.`);
    } catch (error) {
      deletionError = error instanceof Error ? error.message : String(error);
    }
  }
  state.chat.conversationId = null;
  state.chat.visualizationRoute = null;
  for (const message of [...elements.chatTranscript.querySelectorAll(".chat-message")].slice(1)) {
    message.remove();
  }
  elements.chatRouteStatus.textContent = "Waiting";
  elements.statusText.textContent = "Ready for a new Mission";
  elements.chatRouteContext.replaceChildren();
  const empty = document.createElement("div");
  empty.className = "chat-route-empty";
  const glyph = document.createElement("span");
  glyph.setAttribute("aria-hidden", "true");
  glyph.textContent = "◎";
  const title = document.createElement("strong");
  title.textContent = "No Mission routed yet";
  const copy = document.createElement("p");
  copy.textContent = "Your route, Constellation context, available Satellites, and model will appear here.";
  empty.append(glyph, title, copy);
  elements.chatRouteContext.append(empty);
  elements.chatInput.value = "";
  elements.chatInput.focus();
  if (deletionError) {
    appendChatMessage(
      "assistant",
      `The local conversation view was reset, but durable history deletion failed: ${deletionError}`,
      null,
      "error",
    );
  }
}

async function routeThroughEntrypoint() {
  const objective = elements.entryObjective.value.trim();
  if (objective.length < 3) {
    renderEntrypointError("Describe a Mission in at least three characters.");
    return;
  }
  const originalLabel = elements.routeEntry.textContent;
  elements.routeEntry.disabled = true;
  elements.routeEntry.textContent = "Routing…";
  try {
    const response = await fetch("/api/wormhole/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ objective, team_size: 1 }),
    });
    const plan = await response.json();
    if (!response.ok) throw new Error(plan.detail || `Wormhole returned ${response.status}.`);
    applyEntrypointRoute(plan);
    renderEntrypointResult(plan);
  } catch (error) {
    renderEntrypointError(error instanceof Error ? error.message : String(error));
  } finally {
    elements.routeEntry.disabled = false;
    elements.routeEntry.textContent = originalLabel;
  }
}

function applyEntrypointRoute(plan) {
  const galaxyNodeId = `galaxy:${plan.galaxy_id}`;
  const nodeIds = new Set([plan.wormhole_id, galaxyNodeId]);
  const edgeKeys = new Set();
  edgeKeys.add(relationshipKey(plan.wormhole_id, galaxyNodeId));
  for (const path of plan.paths || []) {
    const circleNodeId = `guild:${path.circle_id}`;
    const specialistNodeId = `specialist:${path.specialist_id}`;
    nodeIds.add(circleNodeId);
    nodeIds.add(specialistNodeId);
    edgeKeys.add(relationshipKey(galaxyNodeId, circleNodeId));
    edgeKeys.add(relationshipKey(circleNodeId, specialistNodeId));
  }
  for (const nodeId of nodeIds) state.positions.delete(nodeId);
  state.entryRouting = { nodeIds, edgeKeys, plan };
  state.enabledKinds.add("service");
  state.enabledKinds.add("galaxy");
  state.enabledKinds.add("guild");
  state.enabledKinds.add("specialist");
  state.domain = "all";
  state.query = "";
  state.focusId = null;
  state.selectedId = null;
  elements.domainFilter.value = "all";
  elements.search.value = "";
  renderTypeFilters();
  applyFilters();
  window.setTimeout(() => fitView(), 100);
}

function renderEntrypointResult(plan) {
  elements.entryResult.replaceChildren();
  elements.entryResult.className = "entry-result";
  const summary = document.createElement("div");
  summary.className = "entry-summary";
  const copy = document.createElement("span");
  const strong = document.createElement("strong");
  strong.textContent = "Route ready";
  copy.append(strong, document.createTextNode(" · select the Rocky Planet to inspect or run it"));
  const clear = document.createElement("button");
  clear.className = "entry-clear";
  clear.type = "button";
  clear.textContent = "Clear route";
  clear.addEventListener("click", clearEntrypointRoute);
  summary.append(copy, clear);
  elements.entryResult.append(summary);

  const circles = new Map((plan.circles || []).map((item) => [item.circle_id, item]));
  const specialists = new Map((plan.candidates || []).map((item) => [item.specialist_id, item]));
  for (const path of plan.paths || []) {
    const circle = circles.get(path.circle_id);
    const specialist = specialists.get(path.specialist_id);
    const row = document.createElement("div");
    row.className = "entry-route";
    const routeCopy = document.createElement("div");
    routeCopy.className = "entry-route-copy";
    const wormhole = document.createElement("strong");
    wormhole.textContent = plan.wormhole_name;
    const firstArrow = document.createElement("span");
    firstArrow.className = "entry-route-arrow";
    firstArrow.textContent = "→";
    const galaxyLabel = document.createElement("span");
    galaxyLabel.textContent = plan.galaxy_name;
    const galaxyArrow = document.createElement("span");
    galaxyArrow.className = "entry-route-arrow";
    galaxyArrow.textContent = "→";
    const circleLabel = document.createElement("span");
    circleLabel.textContent = circle?.display_name || path.circle_id;
    const secondArrow = document.createElement("span");
    secondArrow.className = "entry-route-arrow";
    secondArrow.textContent = "→";
    const specialistLabel = document.createElement("span");
    specialistLabel.textContent = specialist?.display_name || path.specialist_id;
    routeCopy.append(
      wormhole,
      firstArrow,
      galaxyLabel,
      galaxyArrow,
      circleLabel,
      secondArrow,
      specialistLabel,
    );
    const inspect = document.createElement("button");
    inspect.type = "button";
    inspect.textContent = "Inspect";
    inspect.addEventListener("click", () => selectNode(`specialist:${path.specialist_id}`));
    row.append(routeCopy, inspect);
    elements.entryResult.append(row);
  }
}

function renderEntrypointError(message) {
  elements.entryResult.replaceChildren();
  elements.entryResult.className = "entry-result";
  const error = document.createElement("span");
  error.className = "entry-error";
  error.textContent = message;
  elements.entryResult.append(error);
}

function clearEntrypointRoute() {
  state.entryRouting = { nodeIds: new Set(), edgeKeys: new Set(), plan: null };
  elements.entryResult.replaceChildren();
  elements.entryResult.classList.add("hidden");
  applyFilters();
  window.setTimeout(() => fitView(), 100);
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
    label.textContent = LEGEND_LABELS[kind] || kind;
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
    agents: "Planets and their Circles",
    components: "Reusable platform components",
    full: "Complete knowledge graph",
    custom: "Custom constellation view",
  };
  elements.viewTitle.textContent = state.focusId
    ? state.nodeById.get(state.focusId)?.label || "Focused relationships"
    : titles[state.preset] || titles.custom;
}

function graphEntityKey(entity) {
  if (!entity || !entity.kind || !entity.id) return null;
  const key = `${entity.kind}:${entity.id}`;
  return state.nodeById.has(key) ? key : null;
}

function runtimeStatus(event) {
  if (event.status) return String(event.status);
  const action = event.event_type.split(".").at(-1);
  return {
    created: "queued",
    requested: "waiting",
    started: "running",
    completed: "completed",
    failed: "failed",
    blocked: "blocked",
    denied: "denied",
    cancelled: "cancelled",
  }[action] || action;
}

function applyOperationalEvent(event, { addToTimeline = false } = {}) {
  const sequence = Number(event.sequence || 0);
  if (addToTimeline) {
    if (state.operations.events.some((item) => Number(item.sequence) === sequence)) return;
    state.operations.events.push(event);
    state.operations.events.sort((left, right) => Number(left.sequence) - Number(right.sequence));
    if (state.operations.events.length > 500) state.operations.events.splice(0, state.operations.events.length - 500);
  }
  state.operations.lastSequence = Math.max(state.operations.lastSequence, sequence);

  const area = event.event_type.split(".", 1)[0];
  const action = event.event_type.split(".").at(-1);
  const seen = new Set();
  for (const entity of [event.actor, event.subject]) {
    const key = graphEntityKey(entity);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    const current = state.operations.entities.get(key) || {
      entity_key: key,
      kind: entity.kind,
      id: entity.id,
      status: "idle",
      active_run_ids: [],
      event_count: 0,
      error_count: 0,
    };
    const activeRuns = new Set(current.active_run_ids || []);
    if (area === entity.kind && event.run_id) {
      if (action === "started") activeRuns.add(event.run_id);
      if (TERMINAL_ACTIONS.has(action)) activeRuns.delete(event.run_id);
      current.status = activeRuns.size ? "running" : runtimeStatus(event);
    } else if (!current.last_sequence) {
      current.status = "idle";
    }
    current.active_run_ids = [...activeRuns];
    current.event_count += 1;
    current.error_count += ["error", "critical"].includes(event.severity) ? 1 : 0;
    current.last_sequence = sequence;
    current.last_event_type = event.event_type;
    current.summary = event.summary;
    current.mission_id = event.mission_id;
    current.run_id = event.run_id;
    state.operations.entities.set(key, current);
  }

  if (event.mission_id && area === "mission") {
    let mission = state.operations.missions.find((item) => item.mission_id === event.mission_id);
    if (!mission) {
      mission = {
        mission_id: event.mission_id,
        specialist_ids: [],
        run_ids: [],
        event_count: 0,
      };
      state.operations.missions.unshift(mission);
    }
    mission.status = runtimeStatus(event);
    mission.summary = event.summary;
    mission.last_sequence = sequence;
    mission.last_event_type = event.event_type;
    mission.updated_at = event.occurred_at;
    mission.event_count = Number(mission.event_count || 0) + 1;
  }
  if (event.mission_id && event.actor?.kind === "specialist") {
    const mission = state.operations.missions.find((item) => item.mission_id === event.mission_id);
    if (mission && !(mission.specialist_ids || []).includes(event.actor.id)) {
      mission.specialist_ids = [...(mission.specialist_ids || []), event.actor.id];
    }
  }
  addActivityEdge(event);
}

function addActivityEdge(event) {
  const source = graphEntityKey(event.actor);
  const target = graphEntityKey(event.subject);
  if (!source || !target || source === target) return;
  const edge = {
    id: event.event_id,
    source,
    target,
    severity: event.severity,
    sequence: Number(event.sequence || 0),
    eventType: event.event_type,
  };
  state.operations.activityEdges.push(edge);
  if (state.operations.activityEdges.length > 36) state.operations.activityEdges.shift();
}

function resetOperationalProjection() {
  state.operations.entities = new Map();
  state.operations.missions = [];
  state.operations.runs = [];
  state.operations.activityEdges = [];
  state.operations.lastSequence = 0;
}

function loadProjectionSnapshot(snapshot) {
  state.operations.lastSequence = Number(snapshot.last_sequence || 0);
  state.operations.missions = [...(snapshot.missions || [])];
  state.operations.runs = [...(snapshot.runs || [])];
  state.operations.entities = new Map(Object.entries(snapshot.entities || {}));
  state.operations.events = [...(snapshot.recent_events || [])];
  state.operations.activityEdges = [];
  for (const event of state.operations.events.slice(-36)) addActivityEdge(event);
  state.operations.replayCount = state.operations.events.length;
}

async function loadOperationsSnapshot() {
  setStreamState("connecting", "Connecting live stream");
  const response = await fetch("/api/operations/snapshot");
  if (!response.ok) throw new Error(`Operations API returned ${response.status}`);
  const snapshot = await response.json();
  loadProjectionSnapshot(snapshot);
  renderOperations();
  return snapshot;
}

function closeEventStream() {
  if (state.operations.eventSource) state.operations.eventSource.close();
  state.operations.eventSource = null;
}

function connectEventStream() {
  closeEventStream();
  if (state.operations.mode !== "live") return;
  const source = new EventSource(`/api/events/stream?after_sequence=${state.operations.lastSequence}`);
  state.operations.eventSource = source;
  source.onopen = () => setStreamState("live", "Live · local event stream");
  source.onerror = () => setStreamState("reconnecting", "Reconnecting · last state retained");
  const receive = (message) => {
    try {
      const event = JSON.parse(message.data);
      applyOperationalEvent(event, { addToTimeline: true });
      if (state.operations.mode === "live") {
        state.operations.replayCount = state.operations.events.length;
        scheduleOperationsRender();
      }
    } catch (error) {
      setStreamState("stale", `Malformed event · ${error.message}`);
    }
  };
  for (const eventType of STREAM_EVENT_TYPES) source.addEventListener(eventType, receive);
}

function scheduleOperationsRender() {
  if (state.operations.renderFrame !== null) return;
  state.operations.renderFrame = requestAnimationFrame(() => {
    state.operations.renderFrame = null;
    renderOperations();
  });
}

function setStreamState(connection, label) {
  state.operations.connection = connection;
  elements.streamState.textContent = label;
  if (state.operations.mode !== "map") {
    elements.apiState.textContent = connection;
    elements.apiState.className = `health-pill ${connection === "live" ? "ok" : connection === "stale" ? "error" : "loading"}`;
  }
}

async function setMode(mode) {
  if (!new Set(["chat", "map", "live", "replay", "guide"]).has(mode)) return;
  state.operations.mode = mode;
  const operationsMode = mode === "live" || mode === "replay";
  document.body.classList.toggle("operations-mode", operationsMode);
  document.body.classList.toggle("chat-mode", mode === "chat");
  document.body.classList.toggle("guide-mode", mode === "guide");
  document.querySelectorAll(".mode-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  elements.operationsControls.classList.toggle("hidden", !operationsMode);
  elements.timeline.classList.toggle("hidden", !operationsMode);
  elements.chatPanel.classList.toggle("hidden", mode !== "chat");
  elements.guidePanel.classList.toggle("hidden", mode !== "guide");

  if (mode === "chat") {
    closeEventStream();
    document.body.classList.remove("inspector-open");
    elements.streamState.textContent = "Wormhole Chat";
    elements.statusText.textContent = state.chat.conversationId
      ? `Conversation ${shortId(state.chat.conversationId)}`
      : "Ready for a new Mission";
    elements.apiState.textContent = state.chat.gemmaReady ? "Gemma ready" : "Gemma unavailable";
    elements.apiState.className = `health-pill ${state.chat.gemmaReady ? "ok" : "error"}`;
    window.setTimeout(() => elements.chatInput.focus(), 0);
    return;
  }

  if (mode === "guide") {
    closeEventStream();
    document.body.classList.remove("inspector-open");
    elements.streamState.textContent = "Galaxy Guide";
    elements.statusText.textContent = "Canonical terminology reference";
    elements.apiState.textContent = "Reference";
    elements.apiState.className = "health-pill ok";
    return;
  }

  if (mode === "map") {
    closeEventStream();
    setGraphCounters();
    elements.streamState.textContent = "Local Control Room";
    elements.apiState.textContent = "Local graph ready";
    elements.apiState.className = "health-pill ok";
    elements.operationsOverview.classList.add("hidden");
    if (!state.selectedId) elements.inspectorEmpty.classList.remove("hidden");
    applyOperationalHighlights();
    renderActivityEdges();
    return;
  }

  elements.inspectorEmpty.classList.add("hidden");
  if (!state.selectedId) elements.operationsOverview.classList.remove("hidden");
  try {
    if (!state.operations.events.length || mode === "live") await loadOperationsSnapshot();
    if (state.operations.mode !== mode) return;
    if (mode === "live") {
      state.operations.replayCount = state.operations.events.length;
      connectEventStream();
    } else {
      closeEventStream();
      state.operations.replayCount = state.operations.events.length;
      rebuildReplay(state.operations.replayCount);
      setStreamState("replaying", "Replay · durable event history");
    }
    renderOperations();
  } catch (error) {
    setStreamState("stale", "Operations unavailable");
    elements.operationsSummary.textContent = error.message;
  }
}

function rebuildReplay(count) {
  const events = state.operations.events;
  resetOperationalProjection();
  const bounded = Math.max(0, Math.min(Number(count), events.length));
  for (const event of events.slice(0, bounded)) applyOperationalEvent(event);
  state.operations.replayCount = bounded;
  state.operations.replaySequence = bounded ? Number(events[bounded - 1].sequence || 0) : 0;
  renderOperations();
}

function setGraphCounters() {
  elements.statSpecialists.textContent = String(state.graph.counts.specialist || 0);
  const componentCount = state.graph.nodes.length - (state.graph.counts.specialist || 0) - (state.graph.counts.guild || 0);
  elements.statComponents.textContent = String(componentCount);
  elements.statRelations.textContent = String(state.graph.edges.length);
  elements.statSpecialistsLabel.textContent = "rocky planets";
  elements.statComponentsLabel.textContent = "components";
  elements.statRelationsLabel.textContent = "relationships";
}

function renderOperations() {
  if (state.operations.mode === "map") return;
  const missions = [...state.operations.missions].sort(
    (left, right) => Number(right.last_sequence || 0) - Number(left.last_sequence || 0),
  );
  const activeMissionStatuses = new Set(["queued", "routed", "running", "waiting", "awaiting_approval"]);
  const attentionStatuses = new Set(["failed", "blocked", "denied", "waiting", "awaiting_approval"]);
  const activeMissions = missions.filter((mission) => activeMissionStatuses.has(mission.status)).length;
  const runningSpecialists = [...state.operations.entities.values()].filter(
    (entity) => entity.kind === "specialist" && entity.status === "running",
  ).length;
  const attention = missions.filter((mission) => attentionStatuses.has(mission.status)).length;
  elements.statSpecialists.textContent = String(activeMissions);
  elements.statComponents.textContent = String(runningSpecialists);
  elements.statRelations.textContent = String(attention);
  elements.statSpecialistsLabel.textContent = "active missions";
  elements.statComponentsLabel.textContent = "running planets";
  elements.statRelationsLabel.textContent = "attention";

  elements.operationsSummary.textContent = `${activeMissions} active Mission${activeMissions === 1 ? "" : "s"} · sequence ${state.operations.lastSequence}`;
  elements.missionCount.textContent = String(missions.length);
  elements.missionList.replaceChildren();
  for (const mission of missions.slice(0, 10)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `mission-card status-${mission.status || "unknown"}`;
    const title = document.createElement("strong");
    title.textContent = mission.summary || shortId(mission.mission_id);
    const status = document.createElement("span");
    status.className = "runtime-label";
    status.textContent = String(mission.status || "unknown").replaceAll("_", " ");
    const meta = document.createElement("span");
    meta.textContent = `${(mission.specialist_ids || []).length} Planet(s) · ${shortId(mission.mission_id)}`;
    button.append(title, status, meta);
    button.addEventListener("click", () => openMissionReplay(mission.mission_id));
    elements.missionList.append(button);
  }
  if (!missions.length) elements.missionList.append(emptyOperationMessage("No Missions have emitted events yet."));

  const visibleEvents = filteredOperationalEvents().slice(-12).reverse();
  elements.eventCount.textContent = String(state.operations.events.length);
  elements.operationsEventList.replaceChildren();
  for (const event of visibleEvents) {
    elements.operationsEventList.append(operationEventButton(event));
  }
  if (!visibleEvents.length) elements.operationsEventList.append(emptyOperationMessage("No events match the current filter."));

  renderTimeline();
  applyOperationalHighlights();
  renderActivityEdges();
  if (state.selectedId) renderNodeActivity(state.nodeById.get(state.selectedId));
}

function filteredOperationalEvents() {
  const status = elements.statusFilter.value;
  const attention = new Set(["failed", "blocked", "denied", "waiting", "awaiting_approval"]);
  return state.operations.events.filter((event) => {
    const eventStatus = runtimeStatus(event);
    if (status !== "all" && eventStatus !== status) return false;
    if (elements.attentionOnly.checked && !attention.has(eventStatus) && !["error", "critical", "warning"].includes(event.severity)) return false;
    return true;
  });
}

function operationEventButton(event) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `operation-event severity-${event.severity || "info"}`;
  const title = document.createElement("strong");
  title.textContent = event.summary;
  const meta = document.createElement("span");
  meta.textContent = `#${event.sequence} · ${event.event_type} · ${formatTime(event.occurred_at)}`;
  button.append(title, meta);
  button.addEventListener("click", () => replayToSequence(Number(event.sequence)));
  return button;
}

function emptyOperationMessage(copy) {
  const message = document.createElement("p");
  message.className = "description";
  message.textContent = copy;
  return message;
}

function renderTimeline() {
  const events = filteredOperationalEvents();
  const replayIndex = state.operations.mode === "live"
    ? events.length
    : events.filter((event) => Number(event.sequence) <= state.operations.replaySequence).length;
  elements.timelineTitle.textContent = state.operations.mode === "live" ? "Live events" : "Deterministic replay";
  elements.timelineScrubber.max = String(events.length);
  elements.timelineScrubber.value = String(replayIndex);
  elements.timelinePosition.textContent = `${replayIndex} / ${events.length}`;
  elements.jumpLive.classList.toggle("hidden", state.operations.mode === "live");
  elements.eventRail.replaceChildren();
  const start = Math.max(0, events.length - 36);
  events.slice(start).forEach((event, offset) => {
    const absoluteIndex = start + offset + 1;
    const button = document.createElement("button");
    button.type = "button";
    button.className = `event-chip ${event.severity || "info"}${absoluteIndex === replayIndex ? " active" : ""}`;
    const title = document.createElement("strong");
    title.textContent = event.event_type;
    const meta = document.createElement("span");
    meta.textContent = `#${event.sequence} · ${formatTime(event.occurred_at)}`;
    button.append(title, meta);
    button.addEventListener("click", () => replayToSequence(Number(event.sequence)));
    elements.eventRail.append(button);
  });
  if (state.operations.mode === "live" && elements.followLive.checked) {
    elements.eventRail.scrollLeft = elements.eventRail.scrollWidth;
  }
}

async function openMissionReplay(missionId) {
  await setMode("replay");
  const response = await fetch(`/api/missions/${encodeURIComponent(missionId)}/timeline?limit=2000`);
  if (!response.ok) return;
  const payload = await response.json();
  state.operations.events = payload.events || [];
  state.operations.replayCount = state.operations.events.length;
  elements.timelineTitle.textContent = `Mission ${shortId(missionId)}`;
  rebuildReplay(state.operations.replayCount);
}

async function runFleetValidation() {
  if (state.operations.mode !== "live") await setMode("live");
  const originalLabel = elements.testAllAgents.textContent;
  elements.testAllAgents.disabled = true;
  elements.testAllAgents.textContent = "Testing all planets…";
  elements.fleetTestResult.className = "fleet-test-result";
  elements.fleetTestResult.replaceChildren();
  const pending = document.createElement("strong");
  pending.textContent = "Fleet validation running";
  const note = document.createElement("span");
  note.textContent = "All compiled Rocky Planets are being checked in safe no-model, no-network mode.";
  elements.fleetTestResult.append(pending, note);
  elements.fleetTestResult.classList.remove("hidden");
  try {
    const response = await fetch("/api/fleet/test", { method: "POST" });
    const report = await response.json();
    if (!response.ok) throw new Error(report.detail || `Fleet validation failed (${response.status}).`);
    renderFleetValidationResult(report);
  } catch (error) {
    elements.fleetTestResult.className = "fleet-test-result failed";
    elements.fleetTestResult.replaceChildren();
    const heading = document.createElement("strong");
    heading.textContent = "Validation request failed";
    const detail = document.createElement("span");
    detail.textContent = error instanceof Error ? error.message : String(error);
    elements.fleetTestResult.append(heading, detail);
  } finally {
    elements.testAllAgents.disabled = false;
    elements.testAllAgents.textContent = originalLabel;
  }
}

function renderFleetValidationResult(report) {
  const passed = report.status === "passed" && report.failed_count === 0;
  elements.fleetTestResult.className = `fleet-test-result${passed ? "" : " failed"}`;
  elements.fleetTestResult.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = passed ? "All planets passed" : `${report.failed_count} planet(s) failed`;
  const detail = document.createElement("span");
  detail.textContent = `${report.passed_count}/${report.tested_count} passed · ${Math.round(report.duration_ms)} ms · ${shortId(report.validation_id)}`;
  elements.fleetTestResult.append(heading, detail);
  const failures = (report.results || []).filter((item) => !item.passed).slice(0, 8);
  for (const failure of failures) {
    const row = document.createElement("span");
    row.textContent = `${failure.specialist_name}: ${failure.error_type || failure.outcome}`;
    elements.fleetTestResult.append(row);
  }
}

function replayToSequence(sequence) {
  if (state.operations.mode !== "replay") {
    setMode("replay").then(() => replayToSequence(sequence));
    return;
  }
  const count = state.operations.events.filter((event) => Number(event.sequence) <= sequence).length;
  rebuildReplay(count);
}

function applyOperationalHighlights() {
  for (const node of state.visibleNodes) {
    const element = state.nodeElements.get(node.id);
    if (!element) continue;
    for (const className of [...element.classList]) {
      if (className.startsWith("runtime-")) element.classList.remove(className);
    }
    if (state.operations.mode === "map") continue;
    const activity = state.operations.entities.get(node.id);
    const status = String(activity?.status || "idle");
    if (activity && status !== "idle") element.classList.add(`runtime-${status}`);
    const selectedStatus = elements.statusFilter.value;
    const attention = new Set(["failed", "blocked", "denied", "waiting", "awaiting_approval"]);
    const filtered = (selectedStatus !== "all" && status !== selectedStatus)
      || (elements.attentionOnly.checked && !attention.has(status));
    element.classList.toggle("runtime-filtered", filtered);
    element.setAttribute("aria-label", `${node.label}, ${KIND_LABELS[node.kind] || node.kind}, runtime ${status}`);
  }
}

function renderActivityEdges() {
  elements.activityEdgeLayer.replaceChildren();
  state.operations.activityEdgeElements.clear();
  if (state.operations.mode === "map") return;
  const visibleIds = new Set(state.visibleNodes.map((node) => node.id));
  for (const edge of state.operations.activityEdges) {
    if (!visibleIds.has(edge.source) || !visibleIds.has(edge.target)) continue;
    const line = svgElement("line", {
      class: `activity-edge ${["error", "critical"].includes(edge.severity) ? "error" : edge.severity === "warning" ? "warning" : ""}`,
      "data-activity-id": edge.id,
    });
    elements.activityEdgeLayer.append(line);
    state.operations.activityEdgeElements.set(edge.id, line);
  }
  updateActivityEdgeElements();
}

function updateActivityEdgeElements() {
  for (const edge of state.operations.activityEdges) {
    const element = state.operations.activityEdgeElements.get(edge.id);
    const source = state.positions.get(edge.source);
    const target = state.positions.get(edge.target);
    if (!element || !source || !target) continue;
    element.setAttribute("x1", source.x);
    element.setAttribute("y1", source.y);
    element.setAttribute("x2", target.x);
    element.setAttribute("y2", target.y);
  }
}

function renderNodeActivity(node) {
  if (!node || state.operations.mode === "map") {
    elements.activitySection.classList.add("hidden");
    return;
  }
  const activity = state.operations.entities.get(node.id);
  const events = state.operations.events.filter((event) => (
    graphEntityKey(event.actor) === node.id || graphEntityKey(event.subject) === node.id
  )).slice(-8).reverse();
  elements.activitySection.classList.remove("hidden");
  elements.activityStatus.textContent = activity?.status || "idle";
  elements.activityList.replaceChildren();
  for (const event of events) elements.activityList.append(operationEventButton(event));
  if (!events.length) elements.activityList.append(emptyOperationMessage("No retained activity for this entity."));
}

function shortId(identifier) {
  const value = String(identifier || "unknown");
  return value.length > 18 ? `${value.slice(0, 9)}…${value.slice(-6)}` : value;
}

function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "unknown time" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
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
  document.querySelectorAll(".mode-button").forEach((button) => {
    button.addEventListener("click", () => setMode(button.dataset.mode));
  });
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
  elements.reduceMotion.addEventListener("change", () => {
    document.body.classList.toggle("reduce-motion", elements.reduceMotion.checked);
    startSimulation(0.08);
  });
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
    document.body.classList.remove("inspector-open");
    elements.inspector.classList.add("hidden");
    if (state.operations.mode === "map") {
      elements.inspectorEmpty.classList.remove("hidden");
      elements.operationsOverview.classList.add("hidden");
    } else {
      elements.inspectorEmpty.classList.add("hidden");
      elements.operationsOverview.classList.remove("hidden");
    }
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
  elements.missionModel.addEventListener("change", updateMissionModelControl);
  elements.routeEntry.addEventListener("click", routeThroughEntrypoint);
  elements.entryObjective.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      routeThroughEntrypoint();
    }
  });
  elements.chatForm.addEventListener("submit", submitChat);
  elements.chatInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitChat(event);
    }
  });
  elements.newChat.addEventListener("click", resetChat);
  elements.closeInspector.addEventListener("click", () => {
    document.body.classList.remove("inspector-open");
  });
  elements.statusFilter.addEventListener("change", renderOperations);
  elements.attentionOnly.addEventListener("change", renderOperations);
  elements.followLive.addEventListener("change", renderTimeline);
  elements.jumpLive.addEventListener("click", () => setMode("live"));
  elements.testAllAgents.addEventListener("click", runFleetValidation);
  elements.timelineScrubber.addEventListener("input", () => {
    const filtered = filteredOperationalEvents();
    const position = Number(elements.timelineScrubber.value);
    if (position <= 0) {
      if (state.operations.mode !== "replay") {
        setMode("replay").then(() => rebuildReplay(0));
      } else {
        rebuildReplay(0);
      }
      return;
    }
    const event = filtered[Math.min(position, filtered.length) - 1];
    if (event) replayToSequence(Number(event.sequence));
  });

  window.addEventListener("resize", () => {
    startSimulation(0.15);
    window.setTimeout(() => fitView(), 100);
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "/" && state.operations.mode !== "chat" && document.activeElement !== elements.search) {
      event.preventDefault();
      elements.search.focus();
    }
    if (event.key === "Escape") {
      document.body.classList.remove("inspector-open");
      elements.search.value = "";
      state.query = "";
      state.focusId = null;
      applyFilters();
    }
  });
}

async function initialize() {
  bindEvents();
  loadGemmaStatus();
  try {
    const response = await fetch("/api/knowledge-graph");
    if (!response.ok) throw new Error(`Graph API returned ${response.status}`);
    const graph = await response.json();
    state.graph = graph;
    state.nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
    setGraphCounters();
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
