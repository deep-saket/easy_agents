# MailMind Scope Mapping

This document maps the target MailMind scope from [mailmindscope.md](/Users/saketm10/Projects/openclaw_agents/agents/mailmind/mailmindscope.md) to what currently exists in this repository.

## Summary

MailMind's target flow remains:

`Read -> Decide -> Draft -> Approve -> Execute`

What exists today is split across two places:

- `agents/mailmind/`
  - MailMind-specific prompt and classification logic
- `src/`
  - shared framework infrastructure, Gmail integrations, tools, memory, nodes, storage, and LLM adapters

The repository is no longer in the old "MailMind agent package under `src.mailmind`" shape. That package has been removed. MailMind now exists as a thin domain layer on top of the shared framework.

## Current MailMind Surface

MailMind-specific code currently present:

- classifier payload and classifier implementation in [email_classifier.py](/Users/saketm10/Projects/openclaw_agents/agents/mailmind/helpers/email_classifier.py)
- classifier prompts in [email_classifier.py](/Users/saketm10/Projects/openclaw_agents/agents/mailmind/prompts/email_classifier.py)
- class metadata in [email_classifier_classes.json](/Users/saketm10/Projects/openclaw_agents/agents/mailmind/prompts/email_classifier_classes.json)
- grouped summary tool in [email_summary.py](/Users/saketm10/Projects/openclaw_agents/agents/mailmind/tools/email_summary.py)
- package exports in [__init__.py](/Users/saketm10/Projects/openclaw_agents/agents/mailmind/__init__.py)

MailMind-specific code not currently present:

- concrete MailMind graph agent
- MailMind planner
- MailMind CLI/runtime entrypoint
- MailMind-specific approval orchestration

## Capability Mapping

### 1. Email Ingestion

Scope requirement:

- fetch emails from Gmail
- normalize into structured email records
- store messages for downstream classification/search
- optionally write memory about ingestion events

Currently present:

- Gmail-backed source in [gmail.py](/Users/saketm10/Projects/openclaw_agents/src/sources/gmail.py)
- email source protocol in [email.py](/Users/saketm10/Projects/openclaw_agents/src/interfaces/email.py)
- normalized email model in [domain.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/domain.py)
- fetch tool in [gmail_fetch.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/gmail_fetch.py)
- repository/storage layer in [duckdb_store.py](/Users/saketm10/Projects/openclaw_agents/src/storage/duckdb_store.py)

Missing or not yet MailMind-specific:

- explicit ingestion-to-memory write policy
- MailMind-specific ingestion orchestration around fetch/classify/notify

Status:

- strongly present at the framework/tool level
- MailMind-specific orchestration missing

### 2. Email Understanding / Classification

Scope requirement:

- classify emails by category
- determine `requires_action`
- determine `action_type`
- compute `impact_score`
- compute `priority_score`
- provide short reasoning

Currently present:

- MailMind-specific structured payload in [email_classifier.py](/Users/saketm10/Projects/openclaw_agents/agents/mailmind/helpers/email_classifier.py)
- MailMind classifier implementation in [email_classifier.py](/Users/saketm10/Projects/openclaw_agents/agents/mailmind/helpers/email_classifier.py)
- shared classifier protocol in [email.py](/Users/saketm10/Projects/openclaw_agents/src/interfaces/email.py)
- classifier execution tool in [email_classifier.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/email_classifier.py)
- shared classification result model in [domain.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/domain.py)
- reusable prompt-based classifier template in [llm_classifier_template.py](/Users/saketm10/Projects/openclaw_agents/src/helpers/llm_classifier_template.py)

Current MailMind classification payload fields:

- `category`
- `requires_action`
- `action_type`
- `impact_score`
- `priority_score`
- `confidence`
- `reason`
- `reason_codes`
- `suggested_action`
- `summary`

Gap versus scope:

- the core classification schema now matches the scope well
- remaining gap is reliability/tuning of the LLM behavior, not schema shape

Status:

- strongly present

### 3. Email Querying

Scope requirement:

- support conversational retrieval
- answer queries like "what emails today?" and "show job emails"
- support sender/category/time filtering
- surface "important" mail
- ideally support grouped output views

Currently present:

- email search tool in [email_search.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/email_search.py)
- repository search methods in [duckdb_store.py](/Users/saketm10/Projects/openclaw_agents/src/storage/duckdb_store.py)
- tool I/O schemas in [tool_io.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/tool_io.py)
- graph runtime in [graph_agent.py](/Users/saketm10/Projects/openclaw_agents/src/agents/graph_agent.py)

Missing or partial:

- MailMind-specific grouped conversational presentation
- richer semantic interpretation of "important"
- a concrete MailMind query-facing agent that routes these tools

Status:

- strong infrastructure present
- MailMind query behavior still missing

### 4. Email Summarization

Scope requirement:

- daily summary
- grouped summary
- individual email summary

Currently present:

- email summary tool in [email_summary.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/email_summary.py)
- MailMind-specific grouped summary tool in [email_summary.py](/Users/saketm10/Projects/openclaw_agents/agents/mailmind/tools/email_summary.py)
- summary/detail output schemas in [emails.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/emails.py)
- summary tool I/O in [tool_io.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/tool_io.py)

Missing or partial:

- daily scheduled summary workflow
- summary policy tuned for MailMind decision-making

Status:

- strongly present for grouped and per-email summaries
- daily workflow still missing

### 5. Response Drafting

Scope requirement:

- generate reply drafts
- adapt tone
- include context from the email/classification

Currently present:

- draft tool in [draft_reply.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/draft_reply.py)
- draft model in [domain.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/domain.py)
- draft generator protocol in [email.py](/Users/saketm10/Projects/openclaw_agents/src/interfaces/email.py)
- simple built-in draft generator in [draft_reply.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/draft_reply.py)

Missing or partial:

- high-quality MailMind-specific draft generation policy
- tone control
- user/persona preference injection

Status:

- partially present

### 6. Approval-Gated Email Sending

Scope requirement:

- no auto-send
- explicit approval before execution
- approval-aware draft/send flow

Currently present:

- approval models in [domain.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/domain.py)
- approval queue protocol in [email.py](/Users/saketm10/Projects/openclaw_agents/src/interfaces/email.py)
- email sender protocol in [email.py](/Users/saketm10/Projects/openclaw_agents/src/interfaces/email.py)
- send result model in [domain.py](/Users/saketm10/Projects/openclaw_agents/src/schemas/domain.py)
- send tool in [email_send.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/email_send.py)
- Gmail sender adapter in [gmail_sender.py](/Users/saketm10/Projects/openclaw_agents/src/sources/gmail_sender.py)
- notification tool with approval lookup in [notification.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/notification.py)
- approval node primitive in [approval_node.py](/Users/saketm10/Projects/openclaw_agents/src/nodes/approval_node.py)

Missing:

- concrete approval queue implementation wired for MailMind
- end-to-end MailMind approval gated execution flow

Status:

- shared send primitives present, MailMind workflow missing

### 7. Notification (WhatsApp)

Scope requirement:

- notify on `requires_action == true`
- notify on high-impact messages
- use WhatsApp as the user-facing approval/attention channel

Currently present:

- WhatsApp interfaces in [whatsapp.py](/Users/saketm10/Projects/openclaw_agents/src/interfaces/whatsapp.py)
- WhatsApp node in [whatsapp_node.py](/Users/saketm10/Projects/openclaw_agents/src/nodes/whatsapp_node.py)
- notification tool in [notification.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/notification.py)
- webhook entrypoint in [whatsapp.py](/Users/saketm10/Projects/openclaw_agents/endpoints/whatsapp.py)

Missing or partial:

- MailMind-specific notification trigger policy
- orchestration that converts classified email events into approval/notification items

Status:

- partially present

### 8. Memory Integration

Scope requirement:

- write episodic/error/user-decision memory
- read user preferences and prior interactions

Currently present:

- shared layered memory system under [memory/](/Users/saketm10/Projects/openclaw_agents/src/memory)
- memory search tool in [memory_search.py](/Users/saketm10/Projects/openclaw_agents/src/tools/memory_search.py)
- memory write tool in [memory_write.py](/Users/saketm10/Projects/openclaw_agents/src/tools/memory_write.py)
- memory retrieval node in [memory_retrieve_node.py](/Users/saketm10/Projects/openclaw_agents/src/nodes/memory_retrieve_node.py)

Missing or partial:

- MailMind-specific memory policy for email decisions and user preferences
- explicit write points integrated into MailMind email workflows

Status:

- strong infrastructure present
- MailMind-specific memory policy missing

## Tool Mapping

From the scope document:

- `EmailFetchTool`
  - present as [gmail_fetch.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/gmail_fetch.py)
- `EmailNormalizeTool`
  - effectively absorbed into [gmail.py](/Users/saketm10/Projects/openclaw_agents/src/sources/gmail.py), which already normalizes Gmail payloads into `EmailMessage`
- `EmailClassifierTool`
  - present as [email_classifier.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/email_classifier.py)
- `EmailSearchTool`
  - present as [email_search.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/email_search.py)
- `EmailSummaryTool`
  - present as [email_summary.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/email_summary.py)
- `MailMindGroupedSummaryTool`
  - present as [email_summary.py](/Users/saketm10/Projects/openclaw_agents/agents/mailmind/tools/email_summary.py)
- `DraftReplyTool`
  - present as [draft_reply.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/draft_reply.py)
- `EmailSendTool`
  - present as [email_send.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/email_send.py)
- `WhatsAppNotifyTool`
  - partially covered by [notification.py](/Users/saketm10/Projects/openclaw_agents/src/tools/gmail/notification.py)
- `MemoryWriteTool`
  - present as [memory_write.py](/Users/saketm10/Projects/openclaw_agents/src/tools/memory_write.py)
- `MemorySearchTool`
  - present as [memory_search.py](/Users/saketm10/Projects/openclaw_agents/src/tools/memory_search.py)

## LLM Mapping

LLM support currently present in the shared framework:

- local Hugging Face inference in [huggingface.py](/Users/saketm10/Projects/openclaw_agents/src/llm/huggingface.py)
- Qwen-specific local adapter in [qwen.py](/Users/saketm10/Projects/openclaw_agents/src/llm/qwen.py)
- function-calling local adapter in [function_gemma.py](/Users/saketm10/Projects/openclaw_agents/src/llm/function_gemma.py)
- hosted/custom endpoint adapters in [remote_llm.py](/Users/saketm10/Projects/openclaw_agents/src/llm/remote_llm.py)
- OpenAI and Groq-compatible hosted adapters in [remote_llm.py](/Users/saketm10/Projects/openclaw_agents/src/llm/remote_llm.py)

MailMind currently uses these through the classifier helper, not through a dedicated MailMind runtime.

## What Is Actually Missing For MailMind

The main missing pieces are no longer basic framework primitives. They are domain assembly and workflow policy:

- a concrete MailMind graph agent
- MailMind-specific planner/routing behavior
- MailMind-specific grouped query and summary views
- MailMind-specific memory write/read policy
- MailMind-specific notification trigger policy
- approval-gated send workflow

## Bottom Line

Current reality:

- the shared framework already provides most of the reusable infrastructure MailMind needs
- MailMind-specific classification is implemented
- MailMind-specific grouped summary behavior is implemented
- Gmail ingestion/search/summary/draft/send/notification primitives are implemented
- the missing layer is the fully assembled MailMind workflow agent

So the repository is no longer "MailMind missing almost everything". It is now closer to:

- framework: mostly ready
- MailMind classifier/prompt layer: ready
- MailMind summary layer: partially ready
- MailMind end-to-end workflow runtime: still missing
