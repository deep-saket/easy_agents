# MailMind Scope Document (mainmindscope.md)

## 1. Overview

MailMind is a **WhatsApp-first, domain-specific email agent** designed to:

- identify **what matters**
- determine **what requires action**
- surface **high-impact opportunities**
- assist in **decision-making and response execution**

MailMind is NOT a general assistant.
MailMind is NOT an orchestrator.

MailMind is a **decision-oriented email workflow agent**.

---

## 2. Core Use Case

The primary use case:

> Reduce cognitive load of email by filtering noise, highlighting action, and assisting execution.

MailMind must answer:

- What requires my attention?
- What requires my action?
- What could benefit me if I act?

---

## 3. Capability Model

MailMind operates across **5 precise capabilities**.

---

### 3.1 Email Ingestion

**Purpose:** Acquire and normalize incoming emails.

Capabilities:
- fetch emails (Gmail)
- normalize into structured format
- store as episodic memory

Output:
- structured email objects

---

### 3.2 Email Understanding (Classification)

**Purpose:** Convert raw emails into actionable intelligence.

Each email must be evaluated on:

#### A. Category
- job
- event
- networking
- personal-important
- low-priority

#### B. Actionability
- requires_action: true/false
- action_type:
  - reply
  - schedule
  - review
  - none

#### C. Impact
- impact_score (0–1)

#### D. Priority
- priority_score (0–1)

#### E. Reasoning
- short explanation

---

### 3.3 Email Querying

**Purpose:** Enable conversational retrieval.

Supported queries:

- "what emails today?"
- "show job emails"
- "important emails"
- "emails from X"

Behavior:
- grouped output:
  - Action Required
  - High Impact
  - Informational

---

### 3.4 Email Summarization

**Purpose:** Provide structured summaries.

Types:
- daily summary
- grouped summary
- individual email summary

---

### 3.5 Response Drafting

**Purpose:** Assist user in replying.

Capabilities:
- generate draft replies
- adapt tone
- include context

---

### 3.6 Approval-Gated Email Sending

Rules:
- NO auto-send
- ALWAYS require explicit approval

Flow:
1. draft generated
2. shown via WhatsApp
3. user approves
4. EmailSendTool executes

---

### 3.7 Notification (WhatsApp)

Trigger:
- requires_action == true
- OR high impact

---

### 3.8 Memory Integration

Write:
- episodic memory
- error memory
- user decisions

Read:
- past interactions
- preferences

---

## 4. Tooling

Email:
- EmailFetchTool
- EmailNormalizeTool

Classification:
- EmailClassifierTool

Query:
- EmailSearchTool
- EmailSummaryTool

Draft:
- DraftReplyTool

Send:
- EmailSendTool

Notify:
- WhatsAppNotifyTool

Memory:
- MemoryWriteTool
- MemorySearchTool

---

## 5. Conversational Behavior

- multi-turn support
- context awareness
- clarification prompts

---

## 6. Constraints

- no autonomous send
- tool-only execution
- logging mandatory
- memory mandatory

---

## 7. Non-Goals

- no coding tasks
- no research tasks
- no orchestration

---

## 8. Success Criteria

- inbox usage reduced
- important emails surfaced
- drafts usable
- minimal user effort

---

## 9. Summary

MailMind is a:

- WhatsApp-first
- decision-centric
- tool-driven
- approval-based agent

Flow:

Read → Decide → Draft → Approve → Execute
