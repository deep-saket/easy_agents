const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const chatLog = document.getElementById("chatLog");
const executionChart = document.getElementById("executionChart");
const executionNarrative = document.getElementById("executionNarrative");
const thinkingTrace = document.getElementById("thinkingTrace");
const snapshotPicker = document.getElementById("snapshotPicker");
const stateJson = document.getElementById("stateJson");
const memoryJson = document.getElementById("memoryJson");
const nodesExplored = document.getElementById("nodesExplored");
const nodeOutputJson = document.getElementById("nodeOutputJson");
const nodeDiffJson = document.getElementById("nodeDiffJson");
const collapseButton = document.getElementById("collapseButton");
const appShell = document.getElementById("appShell");
const sessionIdInput = document.getElementById("sessionId");
const demoUsersEl = document.getElementById("demoUsers");
const llmStatusEl = document.getElementById("llmStatus");

const viewState = {
  snapshots: [],
  nodeEntries: [],
  selectedNodeId: null,
  liveHops: [],
  collapsed: false,
  demoUsers: [],
};

function addBubble(role, text) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.textContent = text;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function renderExecutionChart(hops) {
  executionChart.innerHTML = "";
  if (!hops.length) {
    executionChart.textContent = "No execution hops yet.";
    return;
  }

  for (const hop of hops) {
    const row = document.createElement("div");
    row.className = "hop-row";

    const nodeHistory = Array.isArray(hop.node_history) ? hop.node_history.join(" -> ") : "";
    const toolCalls = (hop.events || [])
      .filter((event) => event.event === "tool_call")
      .map((event) => `${event.tool_name} [${event.status}]`)
      .join(" | ");

    row.innerHTML = `
      <div class="hop-title">Hop ${hop.hop}: target=${hop.response_target} | elapsed=${formatMs(hop.elapsed_ms)}</div>
      <div class="hop-nodes">Nodes: ${nodeHistory || "(none)"}</div>
      <div class="hop-tools">Tools: ${toolCalls || "(none)"}</div>
    `;
    executionChart.appendChild(row);
  }
}

function formatMs(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`;
  return `${Math.round(value)}ms`;
}

function summarizePlan(planProposal) {
  if (!planProposal || typeof planProposal !== "object") return "(no plan)";
  const outline = String(planProposal.plan_outline || "").trim();
  if (outline) return outline;
  const actions = Array.isArray(planProposal.next_actions) ? planProposal.next_actions : [];
  if (actions.length) return `next actions: ${actions.join(", ")}`;
  const intent = String(planProposal.intent || "").trim();
  return intent ? `intent: ${intent}` : "(no plan)";
}

function summarizeToolReason(state) {
  const decision = state && typeof state === "object" ? state.decision : null;
  if (!decision || typeof decision !== "object") return null;
  const thought = String(decision.thought || "").trim();
  const toolCall = decision.tool_call && typeof decision.tool_call === "object" ? decision.tool_call : null;
  if (!toolCall) return thought || null;
  const toolName = String(toolCall.tool_name || "").trim();
  const args = toolCall.arguments ? JSON.stringify(toolCall.arguments) : "{}";
  if (thought) return `Executing ${toolName} because: ${thought} | args=${args}`;
  return `Executing ${toolName} | args=${args}`;
}

function renderExecutionNarrative(hops) {
  executionNarrative.innerHTML = "";
  if (!Array.isArray(hops) || !hops.length) {
    executionNarrative.textContent = "No narrative yet.";
    return;
  }

  const lines = [];
  for (const hop of hops) {
    const state = hop.state || {};
    const nodeHistory = Array.isArray(hop.node_history) ? hop.node_history.join(" -> ") : "(none)";
    const planSummary = summarizePlan(state.plan_proposal);
    const toolReason = summarizeToolReason(state);
    const tools = (hop.events || [])
      .filter((event) => event.event === "tool_call")
      .map((event) => `${event.tool_name} [${event.status}] in ${formatMs(event.duration_ms)}`);
    const nodeDurations = (hop.events || [])
      .filter((event) => event.event === "node_finished")
      .map((event) => `${event.node_name}: ${formatMs(event.duration_ms)}`);
    const phase = String(hop.conversation_phase || "unknown");
    const nodeList = Array.isArray(hop.node_history) ? hop.node_history : [];

    lines.push(`Hop ${hop.hop} started.`);
    lines.push(`Path: ${nodeHistory}`);
    lines.push(`Phase: ${phase}`);
    if (nodeList.includes("plan_proposal")) lines.push("Constructing plan proposal for this turn.");
    if (nodeList.includes("tool_execution")) lines.push("Executing tool calls selected by planner.");
    if (nodeList.includes("relevant_response") || nodeList.includes("irrelevant_response")) {
      lines.push("Constructing final response package.");
    }
    lines.push(`Plan: ${planSummary}`);
    if (toolReason) lines.push(toolReason);
    if (tools.length) lines.push(`Tool results: ${tools.join(" | ")}`);
    if (nodeDurations.length) lines.push(`Node timings: ${nodeDurations.join(" | ")}`);
    lines.push(`Response packaged for target=${hop.response_target} in ${formatMs(hop.elapsed_ms)}.`);
    lines.push(`Output: ${String(hop.response || "").trim() || "(empty response)"}`);
    lines.push("");
  }

  for (const line of lines) {
    const div = document.createElement("div");
    div.className = "narrative-line";
    div.textContent = line;
    executionNarrative.appendChild(div);
  }
  executionNarrative.scrollTop = executionNarrative.scrollHeight;
}

function renderThinking(hops) {
  thinkingTrace.innerHTML = "";
  const lines = [];
  for (const hop of hops) {
    lines.push(`--- hop ${hop.hop} ---`);
    for (const line of hop.thinking || []) {
      lines.push(line);
    }
  }

  if (!lines.length) {
    thinkingTrace.textContent = "No trace yet.";
    return;
  }

  for (const line of lines) {
    const p = document.createElement("div");
    p.className = "trace-line";
    p.textContent = line;
    thinkingTrace.appendChild(p);
  }
  thinkingTrace.scrollTop = thinkingTrace.scrollHeight;
}

function renderSnapshots(hops, finalState, finalMemory) {
  viewState.snapshots = hops.map((hop) => ({
    id: `hop-${hop.hop}`,
    label: `Hop ${hop.hop}`,
    state: hop.state || {},
    memory: hop.working_memory_state || {},
  }));

  viewState.snapshots.push({
    id: "final",
    label: "Final",
    state: finalState || {},
    memory: finalMemory || {},
  });

  snapshotPicker.innerHTML = "";
  for (const snapshot of viewState.snapshots) {
    const option = document.createElement("option");
    option.value = snapshot.id;
    option.textContent = snapshot.label;
    snapshotPicker.appendChild(option);
  }

  snapshotPicker.value = "final";
  renderSelectedSnapshot();
}

function renderSelectedSnapshot() {
  const selected = viewState.snapshots.find((item) => item.id === snapshotPicker.value);
  if (!selected) {
    stateJson.textContent = "{}";
    memoryJson.textContent = "{}";
    return;
  }
  stateJson.textContent = JSON.stringify(selected.state, null, 2);
  memoryJson.textContent = JSON.stringify(selected.memory, null, 2);
}

function flattenState(input, prefix = "", out = {}) {
  if (input === null || input === undefined) {
    out[prefix || "$"] = input;
    return out;
  }
  if (typeof input !== "object") {
    out[prefix || "$"] = input;
    return out;
  }
  if (Array.isArray(input)) {
    out[prefix || "$"] = JSON.stringify(input);
    return out;
  }
  for (const [key, value] of Object.entries(input)) {
    const nextKey = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      flattenState(value, nextKey, out);
    } else {
      out[nextKey] = value;
    }
  }
  return out;
}

function computeStateDiff(prevState, nextState) {
  const prevFlat = flattenState(prevState || {});
  const nextFlat = flattenState(nextState || {});
  const added = [];
  const removed = [];
  const changed = [];

  for (const [key, value] of Object.entries(nextFlat)) {
    if (!(key in prevFlat)) {
      added.push({ key, value });
      continue;
    }
    if (JSON.stringify(prevFlat[key]) !== JSON.stringify(value)) {
      changed.push({ key, before: prevFlat[key], after: value });
    }
  }

  for (const [key, value] of Object.entries(prevFlat)) {
    if (!(key in nextFlat)) {
      removed.push({ key, value });
    }
  }

  return { added, removed, changed };
}

function extractNodeEntries(hops) {
  const entries = [];
  let seq = 0;
  let prevState = {};
  for (const hop of hops || []) {
    const events = Array.isArray(hop.events) ? hop.events : [];
    for (let i = 0; i < events.length; i += 1) {
      const event = events[i] || {};
      if (event.event !== "node_started") continue;

      seq += 1;
      const nodeName = String(event.node_name || "unknown");
      const nodeState = event.state && typeof event.state === "object" ? event.state : {};
      let nodeOutput = {};
      for (let j = i + 1; j < events.length; j += 1) {
        const candidate = events[j] || {};
        if (candidate.event === "node_state" && String(candidate.node_name || "") === nodeName) {
          nodeOutput = candidate;
          break;
        }
      }

      const diff = computeStateDiff(prevState, nodeState);
      entries.push({
        id: `node-${seq}`,
        label: `${seq}. ${nodeName}`,
        hop: hop.hop,
        nodeName,
        state: nodeState,
        output: nodeOutput,
        diff,
      });
      prevState = nodeState;
    }
  }
  return entries;
}

function renderSelectedNodeEntry() {
  const selected = viewState.nodeEntries.find((entry) => entry.id === viewState.selectedNodeId);
  if (!selected) {
    nodeOutputJson.textContent = "{}";
    nodeDiffJson.textContent = "{}";
    return;
  }
  nodeOutputJson.textContent = JSON.stringify(selected.output || {}, null, 2);
  nodeDiffJson.textContent = JSON.stringify(selected.diff || {}, null, 2);
}

function renderNodeExplorer(hops) {
  const entries = extractNodeEntries(hops || []);
  viewState.nodeEntries = entries;
  nodesExplored.innerHTML = "";

  if (!entries.length) {
    nodesExplored.textContent = "No nodes explored yet.";
    nodeOutputJson.textContent = "{}";
    nodeDiffJson.textContent = "{}";
    return;
  }

  if (!viewState.selectedNodeId || !entries.some((entry) => entry.id === viewState.selectedNodeId)) {
    viewState.selectedNodeId = entries[entries.length - 1].id;
  }

  for (const entry of entries) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `node-entry ${entry.id === viewState.selectedNodeId ? "active" : ""}`;
    button.textContent = `Hop ${entry.hop} | ${entry.label}`;
    button.addEventListener("click", () => {
      viewState.selectedNodeId = entry.id;
      renderNodeExplorer(hops);
    });
    nodesExplored.appendChild(button);
  }

  renderSelectedNodeEntry();
}

function setBusy(isBusy) {
  sendButton.disabled = isBusy;
  sendButton.textContent = isBusy ? "Running..." : "Run Turn";
}

function updateLlmStatus(llmMeta) {
  if (!llmMeta) {
    llmStatusEl.textContent = "LLM status: unknown";
    return;
  }

  if (llmMeta.startup_error) {
    llmStatusEl.textContent = `LLM status: fallback mode (startup error: ${llmMeta.startup_error})`;
    return;
  }

  const provider = llmMeta.provider || "configured";
  const model = llmMeta.model_name || "(model not reported)";
  llmStatusEl.textContent = `LLM status: active via ${provider} / ${model}`;
}

function renderTurnPayload(payload) {
  renderExecutionChart(payload.hops || []);
  renderExecutionNarrative(payload.hops || []);
  renderThinking(payload.hops || []);
  renderNodeExplorer(payload.hops || []);
  renderSnapshots(
    payload.hops || [],
    payload.final_state || {},
    payload.final_working_memory_state || {},
  );
  updateLlmStatus(payload.llm || null);
}

function createLiveHop(hop, input) {
  return {
    hop,
    input,
    response: "",
    response_target: "pending",
    elapsed_ms: null,
    node_history: [],
    conversation_phase: "running",
    thinking: [],
    events: [],
    trace_summary: {},
    state: {},
    working_memory_state: {},
  };
}

function findOrCreateLiveHop(hop, input = "") {
  let existing = viewState.liveHops.find((item) => Number(item.hop) === Number(hop));
  if (!existing) {
    existing = createLiveHop(hop, input);
    viewState.liveHops.push(existing);
    viewState.liveHops.sort((a, b) => Number(a.hop) - Number(b.hop));
  }
  return existing;
}

function refreshLivePanels() {
  renderExecutionChart(viewState.liveHops);
  renderExecutionNarrative(viewState.liveHops);
  renderThinking(viewState.liveHops);
  renderNodeExplorer(viewState.liveHops);
  renderSnapshots(viewState.liveHops, {}, {});
}

async function runUserTurn(message) {
  const sessionId = sessionIdInput.value.trim() || "collection-ui-session";
  addBubble("user", message);
  setBusy(true);
  viewState.liveHops = [];
  refreshLivePanels();

  await new Promise((resolve) => {
    const params = new URLSearchParams({
      message,
      session_id: sessionId,
      soft_cap: "10",
      hard_cap: "50",
    });
    const source = new EventSource(`/api/run-turn-stream?${params.toString()}`);
    let finished = false;

    source.addEventListener("hop_started", (evt) => {
      const payload = JSON.parse(evt.data || "{}");
      const hop = Number(payload.hop || 0);
      if (hop > 0) {
        findOrCreateLiveHop(hop, String(payload.input || ""));
        refreshLivePanels();
      }
    });

    source.addEventListener("trace_event", (evt) => {
      const payload = JSON.parse(evt.data || "{}");
      const hop = Number(payload.hop || 0);
      const traceEvent = payload.trace_event || {};
      if (hop > 0) {
        const liveHop = findOrCreateLiveHop(hop);
        liveHop.events.push(traceEvent);
        refreshLivePanels();
      }
    });

    source.addEventListener("hop_update", (evt) => {
      const payload = JSON.parse(evt.data || "{}");
      const hop = Number(payload.hop || 0);
      if (hop > 0) {
        const idx = viewState.liveHops.findIndex((item) => Number(item.hop) === hop);
        if (idx >= 0) {
          viewState.liveHops[idx] = payload;
        } else {
          viewState.liveHops.push(payload);
          viewState.liveHops.sort((a, b) => Number(a.hop) - Number(b.hop));
        }
        refreshLivePanels();
      }
    });

    source.addEventListener("turn_complete", (evt) => {
      const payload = JSON.parse(evt.data || "{}");
      finished = true;
      source.close();
      addBubble("agent", payload.final_response || "No response generated.");
      renderTurnPayload(payload);
      setBusy(false);
      resolve();
    });

    source.addEventListener("turn_error", (evt) => {
      const payload = JSON.parse(evt.data || "{}");
      finished = true;
      source.close();
      addBubble("agent", `Error: ${String(payload.error || "Unknown error")}`);
      setBusy(false);
      resolve();
    });

    source.addEventListener("stream_close", () => {
      if (!finished) {
        source.close();
        setBusy(false);
        resolve();
      }
    });

    source.onerror = () => {
      if (!finished) {
        source.close();
        addBubble("agent", "Error: live stream disconnected.");
        setBusy(false);
        resolve();
      }
    };
  });
}

function renderDemoUsers(users) {
  demoUsersEl.innerHTML = "";

  for (const entry of users) {
    const customer = entry.customer || {};
    const caseInfo = entry.case || {};
    const card = document.createElement("div");
    card.className = "demo-user-card";

    card.innerHTML = `
      <h3>${entry.display_name}</h3>
      <p class="demo-user-meta"><strong>Name:</strong> ${customer.name}</p>
      <p class="demo-user-meta"><strong>Customer ID:</strong> ${customer.customer_id}</p>
      <p class="demo-user-meta"><strong>Case:</strong> ${caseInfo.case_id} (DPD ${caseInfo.dpd})</p>
      <p class="demo-user-meta"><strong>DOB:</strong> ${customer.dob} | <strong>ZIP:</strong> ${customer.zip}</p>
      <p class="demo-user-meta"><strong>PAN last4:</strong> ${customer.last4_pan}</p>
      <p class="demo-user-meta"><strong>Overdue:</strong> ${caseInfo.overdue_amount} | <strong>EMI:</strong> ${caseInfo.emi_amount}</p>
      <div class="demo-user-actions">
        <button type="button" data-user-code="${entry.user_code}">Start As ${entry.display_name}</button>
      </div>
    `;

    const button = card.querySelector("button");
    button.addEventListener("click", () => startDemoConversation(entry));
    demoUsersEl.appendChild(card);
  }
}

async function loadDemoUsers() {
  try {
    const response = await fetch("/api/demo-users");
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }
    const payload = await response.json();
    viewState.demoUsers = Array.isArray(payload.users) ? payload.users : [];
    renderDemoUsers(viewState.demoUsers);
  } catch (error) {
    demoUsersEl.textContent = `Failed to load demo users: ${String(error)}`;
  }
}

async function startDemoConversation(userEntry) {
  const sessionId = `collection-${userEntry.user_code}`;
  sessionIdInput.value = sessionId;
  setBusy(true);

  try {
    const response = await fetch("/api/start-conversation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_code: userEntry.user_code,
        session_id: sessionId,
      }),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }

    const payload = await response.json();
    if (payload.error) {
      throw new Error(payload.error);
    }

    addBubble(
      "system",
      `Initialized ${userEntry.display_name} | case=${userEntry.case.case_id} | customer_id=${userEntry.customer.customer_id}`,
    );

    const turn = payload.turn || {};
    addBubble("agent", turn.final_response || "No opener generated.");
    renderTurnPayload(turn);
  } catch (error) {
    addBubble("agent", `Error starting demo conversation: ${String(error)}`);
  } finally {
    setBusy(false);
  }
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;
  messageInput.value = "";
  await runUserTurn(message);
});

snapshotPicker.addEventListener("change", renderSelectedSnapshot);

collapseButton.addEventListener("click", () => {
  viewState.collapsed = !viewState.collapsed;
  appShell.classList.toggle("collapsed", viewState.collapsed);
  collapseButton.textContent = viewState.collapsed ? "Expand" : "Collapse";
});

renderExecutionChart([]);
renderExecutionNarrative([]);
renderThinking([]);
renderNodeExplorer([]);
renderSnapshots([], {}, {});
loadDemoUsers();
