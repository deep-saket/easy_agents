const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const chatLog = document.getElementById("chatLog");
const executionChart = document.getElementById("executionChart");
const thinkingTrace = document.getElementById("thinkingTrace");
const snapshotPicker = document.getElementById("snapshotPicker");
const stateJson = document.getElementById("stateJson");
const memoryJson = document.getElementById("memoryJson");
const collapseButton = document.getElementById("collapseButton");
const appShell = document.getElementById("appShell");
const sessionIdInput = document.getElementById("sessionId");
const demoUsersEl = document.getElementById("demoUsers");
const llmStatusEl = document.getElementById("llmStatus");

const viewState = {
  snapshots: [],
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
      <div class="hop-title">Hop ${hop.hop}: target=${hop.response_target}</div>
      <div class="hop-nodes">Nodes: ${nodeHistory || "(none)"}</div>
      <div class="hop-tools">Tools: ${toolCalls || "(none)"}</div>
    `;
    executionChart.appendChild(row);
  }
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
  renderThinking(payload.hops || []);
  renderSnapshots(
    payload.hops || [],
    payload.final_state || {},
    payload.final_working_memory_state || {},
  );
  updateLlmStatus(payload.llm || null);
}

async function runUserTurn(message) {
  const sessionId = sessionIdInput.value.trim() || "collection-ui-session";
  addBubble("user", message);
  setBusy(true);

  try {
    const response = await fetch("/api/run-turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        session_id: sessionId,
      }),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }

    const payload = await response.json();
    addBubble("agent", payload.final_response || "No response generated.");
    renderTurnPayload(payload);
  } catch (error) {
    addBubble("agent", `Error: ${String(error)}`);
  } finally {
    setBusy(false);
  }
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
renderThinking([]);
renderSnapshots([], {}, {});
loadDemoUsers();
