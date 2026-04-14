# MailMind Scope Mapping

This document maps the target MailMind scope to what currently exists in the repository.

## Summary

MailMind's target flow remains:

`Read -> Decide -> Draft -> Approve -> Execute`

What exists today is split across:

- `agents/mailmind/`
  - MailMind-specific prompts, classifier logic, agent entrypoint, and tools
- `src/`
  - shared framework infrastructure, Gmail integrations, memory, nodes, storage, and LLM adapters

## Strongly Present

- Gmail ingestion primitives
- MailMind email classification
- email search
- per-email and grouped summary tooling
- draft generation primitives
- shared memory infrastructure
- hosted and local LLM backends

## Partially Present

- MailMind-specific workflow policy
- approval-gated send orchestration
- notification trigger policy
- MailMind memory policy

## Main Gap

The main missing layer is no longer basic infrastructure.

The main gap is the fully assembled MailMind workflow policy across:

- approval
- notification
- memory policy
- execution rules

## Bottom Line

Current reality:

- framework primitives are largely in place
- MailMind-specific classifier and summary layers are in place
- MailMind runtime assembly now exists
- the remaining work is policy and workflow refinement, not basic platform capability
