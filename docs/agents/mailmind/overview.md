# MailMind Overview

MailMind is a WhatsApp-first, domain-specific email workflow agent built on top of the shared `easy_agents` framework.

## Responsibilities

- email classification
- grouped email summarization
- decision-oriented inbox workflows
- draft generation
- approval-gated sending

## Package Surface

Main package entrypoints:

- `MailMindAgent`
- `MailMindEmailClassifier`
- `MailMindEmailClassificationPayload`

MailMind-specific assets currently live under:

- `agents/mailmind/helpers/`
- `agents/mailmind/prompts/`
- `agents/mailmind/tools/`
- `agents/mailmind/nodes/`

## Related Docs

- [MailMind Scope](./scope.md)
- [MailMind Scope Mapping](./scope-mapping.md)
- [MailMind Graph Spec](./graph.md)
