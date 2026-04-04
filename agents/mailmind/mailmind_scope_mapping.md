# MailMind Scope Mapping

This document maps the target MailMind scope from [mailmindscope.md](/Users/saketm10/Projects/openclaw_agents/agents/mailmind/mailmindscope.md) to what currently exists in the shared `src/` framework and what is still missing.

## Summary

MailMind's intended flow is:

`Read -> Decide -> Draft -> Approve -> Execute`

The current `src/` framework already contains many of the primitives MailMind will need:

- graph runtime
- tool registry and executor
- shared email and tool schemas
- repository and storage layers
- WhatsApp interface
- layered memory
- approval primitive

But MailMind itself is not rebuilt yet as a concrete agent. Most of the missing pieces are domain behavior, orchestration, and concrete integrations.

## Capability Mapping

### 1. Email Ingestion

Scope requirement:

- fetch emails (Gmail)
- normalize into structured format
- store as episodic memory

Present in `src/`:

- email message model in [src/schemas/domain.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/domain.py)
- email source protocol in [src/interfaces/email.py](/Users/saketm10/Projects/openclaw_agents/src/interfaces/email.py)
- fetch tool shape in [src/tools/gmail/gmail_fetch.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/gmail_fetch.py)
- persistence layer in [src/storage/duckdb_store.py](/Users/saketm10/Projects/openclaw_agents/src/storage/duckdb_store.py)
- memory infrastructure in [src/memory](/Users/saketm10/Projects/openclaw_agents/src/memory)

Missing:

- concrete Gmail source implementation in current `src/`
- explicit email normalization tool
- MailMind-specific ingestion pipeline that writes episodic memory for incoming mail

Status:

- partially present

### 2. Email Understanding / Classification

Scope requirement:

- category
- requires_action
- action_type
- impact_score
- priority_score
- short explanation

Present in `src/`:

- classification result model in [src/schemas/domain.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/domain.py)
- classifier protocol in [src/interfaces/email.py](/Users/saketm10/Projects/openclaw_agents/src/interfaces/email.py)
- classifier tool in [src/tools/gmail/email_classifier.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/email_classifier.py)

Current schema fields:

- `category`
- `priority_score`
- `confidence`
- `reason_codes`
- `suggested_action`
- `summary`

Missing vs target scope:

- `requires_action`
- `action_type`
- `impact_score`
- explicit short reasoning field matching the new scope
- actual classifier implementation in current `src/`

Status:

- partially present, schema not fully aligned

### 3. Email Querying

Scope requirement:

- conversational retrieval
- queries like:
  - "what emails today?"
  - "show job emails"
  - "important emails"
  - "emails from X"
- grouped output:
  - Action Required
  - High Impact
  - Informational

Present in `src/`:

- search tool in [src/tools/gmail/email_search.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/email_search.py)
- search input/output schemas in [src/schemas/tool_io.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/tool_io.py)
- DuckDB query support in [src/storage/duckdb_store.py](/Users/saketm10/Projects/openclaw_agents/src/storage/duckdb_store.py)
- graph/planner runtime in [src/agents](/Users/saketm10/Projects/openclaw_agents/src/agents)

Missing:

- MailMind-specific query planner behavior
- grouped output by `Action Required / High Impact / Informational`
- domain interpretation of "important"

Status:

- partially to strongly present at the infrastructure level

### 4. Email Summarization

Scope requirement:

- daily summary
- grouped summary
- individual email summary

Present in `src/`:

- summary tool schema in [src/schemas/tool_io.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/tool_io.py)
- summary implementation in [src/tools/gmail/email_summary.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/email_summary.py)
- email detail/summary view models in [src/schemas/emails.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/emails.py)

Missing:

- daily summary behavior
- grouped summary behavior for MailMind categories
- MailMind-specific summarization policy

Status:

- partially present

### 5. Response Drafting

Scope requirement:

- generate draft replies
- adapt tone
- include context

Present in `src/`:

- draft model in [src/schemas/domain.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/domain.py)
- draft generator protocol in [src/interfaces/email.py](/Users/saketm10/Projects/openclaw_agents/src/interfaces/email.py)
- draft tool in [src/tools/gmail/draft_reply.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/draft_reply.py)

Missing:

- concrete draft generator implementation
- tone adaptation behavior
- context-aware drafting policy for MailMind

Status:

- partially present

### 6. Approval-Gated Email Sending

Scope requirement:

- no auto-send
- always require explicit approval
- flow:
  1. draft generated
  2. shown via WhatsApp
  3. user approves
  4. send tool executes

Present in `src/`:

- approval models in [src/schemas/domain.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/domain.py)
- generic approval node in [src/agents/nodes/approval_node.py](/Users/saketm10/Projects/openclaw_agents/src/agents/nodes/approval_node.py)
- notification tool shell in [src/tools/gmail/notification.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/notification.py)

Missing:

- approval queue implementation in current `src/`
- concrete orchestrator/service for the approval flow
- email send tool
- actual MailMind approval-gated send workflow

Status:

- primitives present, workflow missing

### 7. Notification (WhatsApp)

Scope requirement:

- trigger on `requires_action == true` or high impact

Present in `src/`:

- WhatsApp transport abstractions in [src/interfaces/whatsapp.py](/Users/saketm10/Projects/openclaw_agents/src/interfaces/whatsapp.py)
- WhatsApp graph node in [src/agents/nodes/whatsapp_node.py](/Users/saketm10/Projects/openclaw_agents/src/agents/nodes/whatsapp_node.py)
- webhook entrypoint in [endpoints/whatsapp.py](/Users/saketm10/Projects/openclaw_agents/endpoints/whatsapp.py)

Missing:

- MailMind-specific notification trigger policy
- notification orchestration over classified email events

Status:

- partially present

### 8. Memory Integration

Scope requirement:

- write episodic memory
- write error memory
- write user decisions
- read preferences and past interactions

Present in `src/`:

- layered memory system in [src/memory](/Users/saketm10/Projects/openclaw_agents/src/memory)
- memory retrieval node in [src/agents/nodes/memory_retrieve_node.py](/Users/saketm10/Projects/openclaw_agents/src/agents/nodes/memory_retrieve_node.py)
- memory write tool in [src/tools/memory_write.py](/Users/saketm10/Projects/openclaw_agents/src/tools/memory_write.py)
- memory search tool in [src/tools/memory_search.py](/Users/saketm10/Projects/openclaw_agents/src/tools/memory_search.py)

Missing:

- MailMind-specific memory policy for writing user decisions and email-specific events
- explicit preference extraction and retrieval behavior tailored to MailMind

Status:

- strongly present as framework infrastructure

## Tool Mapping

From the scope doc:

- `EmailFetchTool`
  - partial equivalent exists as [src/tools/gmail/gmail_fetch.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/gmail_fetch.py)
- `EmailNormalizeTool`
  - missing
- `EmailClassifierTool`
  - present as [src/tools/gmail/email_classifier.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/email_classifier.py)
- `EmailSearchTool`
  - present as [src/tools/gmail/email_search.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/email_search.py)
- `EmailSummaryTool`
  - present as [src/tools/gmail/email_summary.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/email_summary.py)
- `DraftReplyTool`
  - present as [src/tools/gmail/draft_reply.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/draft_reply.py)
- `EmailSendTool`
  - missing
- `WhatsAppNotifyTool`
  - partially covered by [src/interfaces/whatsapp.py](/Users/saketm10/Projects/openclaw_agents/src/interfaces/whatsapp.py), [src/agents/nodes/whatsapp_node.py](/Users/saketm10/Projects/openclaw_agents/src/agents/nodes/whatsapp_node.py), and [src/tools/gmail/notification.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/notification.py)
- `MemoryWriteTool`
  - present as [src/tools/memory_write.py](/Users/saketm10/Projects/openclaw_agents/src/tools/memory_write.py)
- `MemorySearchTool`
  - present as [src/tools/memory_search.py](/Users/saketm10/Projects/openclaw_agents/src/tools/memory_search.py)

## Behavioral Mapping

Multi-turn support:

- present through [src/agents/graph_agent.py](/Users/saketm10/Projects/openclaw_agents/src/agents/graph_agent.py) and [src/memory/conversation.py](/Users/saketm10/Projects/openclaw_agents/src/memory/conversation.py)

Context awareness:

- present through working memory plus long-term retrieval

Clarification prompts:

- possible with the current graph/planner design, but not implemented specifically for MailMind

Tool-only execution:

- strongly supported by the framework design

Logging mandatory:

- infrastructure exists in [src/platform_logging](/Users/saketm10/Projects/openclaw_agents/src/platform_logging) and tool execution logging exists

Memory mandatory:

- infrastructure exists, but not yet enforced by a MailMind-specific runtime

No autonomous send:

- conceptually compatible with the current design, but not yet implemented as a complete MailMind send workflow

## Bottom Line

What already exists in `src/` for MailMind:

- graph runtime
- tool system
- email and message schemas
- repository protocols and DuckDB storage
- search, summarize, classify, and draft tool shells
- WhatsApp transport and graph node
- layered memory system
- approval primitive

What is still missing for the new MailMind:

- a rebuilt MailMind concrete agent
- Gmail ingestion adapter
- normalization tool
- classifier implementation aligned with the new scope
- MailMind-specific query planner and grouped output behavior
- draft generator implementation
- approval queue and orchestration flow
- email send tool
- MailMind-specific memory and notification policies
