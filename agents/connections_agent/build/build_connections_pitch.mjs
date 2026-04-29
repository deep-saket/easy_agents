import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const W = 1280;
const H = 720;
const OUT_PPTX = "/Users/saketm10/Projects/openclaw_agents/agents/connections_agent/Connections_Agent_Proposal.pptx";
const GRAPH_PATH = "/Users/saketm10/Projects/openclaw_agents/agents/connections_agent/graph.png";

const COLORS = {
  bg: "#F6F8FB",
  title: "#0B1B3A",
  body: "#25324A",
  muted: "#5C6B84",
  accent: "#0E8A5A",
  accentSoft: "#DFF5EC",
  coral: "#E86F5B",
  card: "#FFFFFF",
  line: "#D8E0EE",
  dark: "#0F172A",
};

const FONTS = {
  title: "Poppins",
  body: "Lato",
};

const presentation = Presentation.create({
  slideSize: { width: W, height: H },
});

function shape(slide, geometry, left, top, width, height, fill = COLORS.card, line = COLORS.line, lineWidth = 1) {
  return slide.shapes.add({
    geometry,
    position: { left, top, width, height },
    fill,
    line: { style: "solid", fill: line, width: lineWidth },
  });
}

function text(slide, value, left, top, width, height, opts = {}) {
  const box = shape(slide, "rect", left, top, width, height, opts.fill ?? "#00000000", opts.line ?? "#00000000", opts.lineWidth ?? 0);
  box.text = value;
  box.text.typeface = opts.typeface ?? FONTS.body;
  box.text.fontSize = opts.fontSize ?? 22;
  box.text.color = opts.color ?? COLORS.body;
  box.text.bold = opts.bold ?? false;
  box.text.alignment = opts.align ?? "left";
  box.text.verticalAlignment = opts.valign ?? "top";
  box.text.insets = opts.insets ?? { left: 0, right: 0, top: 0, bottom: 0 };
  return box;
}

function addHeader(slide, title, subtitle, number) {
  slide.background.fill = COLORS.bg;
  shape(slide, "rect", 48, 36, 1184, 48, COLORS.card, COLORS.line, 0.5);
  text(slide, title, 72, 48, 850, 28, {
    typeface: FONTS.title,
    fontSize: 20,
    bold: true,
    color: COLORS.title,
    valign: "middle",
    checkFit: false,
  });
  text(slide, `Slide ${number}`, 1070, 48, 130, 28, {
    fontSize: 14,
    color: COLORS.muted,
    align: "right",
    valign: "middle",
  });
  if (subtitle) {
    text(slide, subtitle, 72, 100, 1130, 26, {
      fontSize: 15,
      color: COLORS.muted,
      valign: "middle",
    });
  }
}

function bulletLines(items) {
  return items.map((line) => `• ${line}`).join("\n");
}

function addCard(slide, x, y, w, h, title, body) {
  shape(slide, "roundRect", x, y, w, h, COLORS.card, COLORS.line, 1);
  text(slide, title, x + 20, y + 16, w - 40, 36, {
    typeface: FONTS.title,
    fontSize: 22,
    bold: true,
    color: COLORS.title,
  });
  text(slide, body, x + 20, y + 60, w - 40, h - 74, {
    typeface: FONTS.body,
    fontSize: 18,
    color: COLORS.body,
  });
}

function addTable(slide, x, y, w, h, headers, rows, colWidths) {
  const rowCount = rows.length + 1;
  const rowH = h / rowCount;
  let cx = x;
  for (let c = 0; c < headers.length; c += 1) {
    const cw = w * colWidths[c];
    shape(slide, "rect", cx, y, cw, rowH, "#EAF2FF", COLORS.line, 1);
    text(slide, headers[c], cx + 8, y + 6, cw - 16, rowH - 12, {
      typeface: FONTS.title,
      fontSize: 13,
      bold: true,
      color: COLORS.title,
      valign: "middle",
    });
    cx += cw;
  }
  for (let r = 0; r < rows.length; r += 1) {
    let xCell = x;
    for (let c = 0; c < headers.length; c += 1) {
      const cw = w * colWidths[c];
      shape(slide, "rect", xCell, y + rowH * (r + 1), cw, rowH, "#FFFFFF", COLORS.line, 0.8);
      text(slide, rows[r][c], xCell + 8, y + rowH * (r + 1) + 5, cw - 16, rowH - 10, {
        fontSize: 11,
        color: COLORS.body,
        valign: "middle",
      });
      xCell += cw;
    }
  }
}

async function addGraphImage(slide, left, top, width, height) {
  const bytes = await fs.readFile(GRAPH_PATH);
  const blob = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const img = slide.images.add({ blob, fit: "contain", alt: "Connections agent runtime graph" });
  img.position = { left, top, width, height };
}

// Slide 1: Title
{
  const s = presentation.slides.add();
  s.background.fill = COLORS.dark;
  shape(s, "rect", 0, 0, W, H, COLORS.dark, COLORS.dark, 0);
  shape(s, "roundRect", 70, 90, 1140, 540, "#13213F", "#1F335F", 1);
  shape(s, "rect", 70, 430, 1140, 200, "#0E8A5A", "#0E8A5A", 0);
  text(s, "Connections Agent", 120, 160, 1000, 90, {
    typeface: FONTS.title,
    fontSize: 58,
    bold: true,
    color: "#FFFFFF",
    valign: "middle",
  });
  text(s, "AI-powered collections workflow for bank recovery operations", 120, 260, 1020, 56, {
    typeface: FONTS.body,
    fontSize: 28,
    color: "#E9EEF8",
  });
  text(s, "Concept deck for leadership review", 120, 492, 1020, 44, {
    typeface: FONTS.body,
    fontSize: 24,
    bold: true,
    color: "#FFFFFF",
    valign: "middle",
  });
}

// Slide 2: Problem
{
  const s = presentation.slides.add();
  addHeader(s, "Why this is needed", "Current collections operations are fragmented and inconsistent", 2);
  addCard(
    s,
    70,
    150,
    550,
    500,
    "Current pain points",
    bulletLines([
      "Manual case handling causes low throughput",
      "Inconsistent borrower conversations across agents",
      "Policy checks happen late and sometimes manually",
      "Follow-ups and promise-to-pay tracking are error-prone",
      "Audit trails are hard to stitch end-to-end",
    ]),
  );
  addCard(
    s,
    660,
    150,
    550,
    500,
    "Business impact",
    bulletLines([
      "Higher collections cost per recovered account",
      "Lower promise-to-pay kept rate",
      "Missed recovery opportunities",
      "Compliance risk due to process variance",
      "Weak visibility for supervisors",
    ]),
  );
}

// Slide 3: Proposed solution
{
  const s = presentation.slides.add();
  addHeader(s, "Proposed solution", "A graph-based agent that mirrors real collections execution", 3);
  addCard(
    s,
    70,
    150,
    360,
    500,
    "What it does",
    bulletLines([
      "Prioritizes defaulter cases",
      "Guides borrower interaction",
      "Executes policy-safe tool calls",
      "Supports payment and follow-up scheduling",
      "Creates structured audit records",
    ]),
  );
  addCard(
    s,
    460,
    150,
    360,
    500,
    "How it runs",
    bulletLines([
      "Memory-aware runtime",
      "React-style planning loop",
      "Tool execution with explicit arguments",
      "Reflection-driven quality gate",
      "Response generation for final communication",
    ]),
  );
  addCard(
    s,
    850,
    150,
    360,
    500,
    "Why it is safer",
    bulletLines([
      "No account disclosure before verification",
      "Deterministic policy authority",
      "Traceable tool outputs and decisions",
      "Escalation path for sensitive cases",
      "Repeatable process across teams",
    ]),
  );
}

// Slide 4: Runtime graph
{
  const s = presentation.slides.add();
  addHeader(s, "Runtime topology", "Exact README graph exported as image", 4);
  shape(s, "roundRect", 55, 145, 1170, 515, COLORS.card, COLORS.line, 1);
  await addGraphImage(s, 70, 155, 1140, 495);
}

// Slide 5: Node responsibilities
{
  const s = presentation.slides.add();
  addHeader(s, "Node-level responsibilities", "Each node has a clear contract", 5);
  const nodes = [
    ["MemoryRetrieveNode", "Fetches prior attempts, promises, and disputes context"],
    ["ReactNode", "Plans next step, chooses tool + arguments, or routes to response"],
    ["ToolExecutionNode", "Executes one selected tool and returns structured observation"],
    ["ReflectNode", "Checks completeness/compliance and decides complete vs incomplete"],
    ["ResponseNode", "Generates concise, policy-safe customer communication"],
  ];
  shape(s, "roundRect", 70, 150, 1140, 500, COLORS.card, COLORS.line, 1);
  let y = 180;
  for (const [name, desc] of nodes) {
    shape(s, "rect", 95, y - 8, 1090, 72, "#00000000", COLORS.line, 0.6);
    text(s, name, 110, y + 8, 300, 38, {
      typeface: FONTS.title,
      fontSize: 20,
      bold: true,
      color: COLORS.title,
      valign: "middle",
    });
    text(s, desc, 430, y + 8, 740, 38, {
      typeface: FONTS.body,
      fontSize: 17,
      color: COLORS.body,
      valign: "middle",
    });
    y += 90;
  }
}

// Slide 6: Tool mapping table (part 1)
{
  const s = presentation.slides.add();
  addHeader(s, "Tool mapping table (1/2)", "Human team activity to tool contract", 6);
  const headers = ["Human Team Activity", "Tool / Agent Tool", "Input", "Output"];
  const rows = [
    ["Get list of defaulters from core systems", "case_fetch", "portfolio_id, dpd_range, optional filters", "ranked case list with dues"],
    ["Decide who to call first", "case_prioritize", "case list + risk signals", "ordered call queue"],
    ["Attempt call / message on preferred channel", "contact_attempt", "case_id, channel, template id", "contact status and attempt id"],
    ["Verify right party and credentials", "customer_verify", "masked identifiers + challenge answers", "verified / failed / locked"],
    ["Read loan policy and EMI context", "loan_policy_lookup", "loan_id", "policy limits and repayment rules"],
    ["Explain due amount and charges", "dues_explain_build", "case_id, locale, policy snapshot", "customer-safe dues script"],
    ["Ask for immediate payment", "payment_link_create", "loan_id, amount, channel, expiry", "signed payment link + reference"],
    ["Confirm payment completion", "payment_status_check", "payment reference", "success / pending / failed"],
  ];
  addTable(s, 65, 150, 1150, 500, headers, rows, [0.31, 0.19, 0.25, 0.25]);
}

// Slide 7: Tool mapping table (part 2)
{
  const s = presentation.slides.add();
  addHeader(s, "Tool mapping table (2/2)", "Human team activity to tool contract", 7);
  const headers = ["Human Team Activity", "Tool / Agent Tool", "Input", "Output"];
  const rows = [
    ["Handle 'cannot pay now' conversation", "negotiation_agent_tool", "case state + conversation context", "recommended next offer/action"],
    ["Check if discount/restructure allowed", "offer_eligibility", "case_id, hardship flags", "allowed offers + reason codes"],
    ["Capture promise to pay on future date", "promise_capture", "date/time, amount, channel", "promise record + confidence"],
    ["Schedule follow-up call/message", "followup_schedule", "case_id, promise date, SLA", "scheduled task id"],
    ["Log final call outcome/disposition", "disposition_update", "disposition code + notes", "persisted status + audit id"],
    ["Escalate disputes/legal/fraud cases", "human_escalation", "reason + evidence summary", "queue assignment id"],
    ["Quality-check risky interactions", "qa_review_agent_tool", "transcript + policy snapshot", "QA score + violations"],
  ];
  addTable(s, 65, 150, 1150, 500, headers, rows, [0.31, 0.19, 0.25, 0.25]);
}

// Slide 8: Sample use case
{
  const s = presentation.slides.add();
  addHeader(s, "Sample scenario", "Borrower cannot pay now and commits after 5 days", 8);
  addCard(
    s,
    70,
    150,
    1140,
    500,
    "Example turn flow",
    bulletLines([
      "Load context: prior promise history and verification status",
      "Fetch current dues and policy window",
      "Check concession eligibility (returns no discount)",
      "Capture promise-to-pay for +5 days",
      "Schedule follow-up reminder and update disposition",
      "Reflect for completeness; if incomplete, loop back to ReactNode",
      "Generate final borrower confirmation message",
    ]),
  );
}

// Slide 9: Roadmap + KPI
{
  const s = presentation.slides.add();
  addHeader(s, "Implementation roadmap", "Phased rollout with measurable business outcomes", 9);
  addCard(
    s,
    70,
    150,
    550,
    240,
    "Phase 1 (MVP)",
    bulletLines([
      "Core tools: fetch, verify, payment link, follow-up",
      "Single channel rollout",
      "Baseline analytics and audit trail",
    ]),
  );
  addCard(
    s,
    70,
    410,
    550,
    240,
    "Phase 2",
    bulletLines([
      "Concession/policy tools",
      "Escalation playbooks",
      "Supervisor QA dashboard",
    ]),
  );
  addCard(
    s,
    660,
    150,
    550,
    500,
    "Success metrics",
    bulletLines([
      "Right-party-contact rate",
      "Promise-to-pay kept rate",
      "Recovery percentage",
      "Average resolution turns",
      "Policy violation attempts blocked",
      "Escalation quality and closure time",
    ]),
  );
}

const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(OUT_PPTX);
console.log(OUT_PPTX);
