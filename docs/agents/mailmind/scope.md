# MailMind Scope

## Overview

MailMind is a WhatsApp-first, domain-specific email agent designed to:

- identify what matters
- determine what requires action
- surface high-impact opportunities
- assist in decision-making and response execution

MailMind is not a general assistant.
MailMind is not an orchestrator.

## Core Use Case

Primary goal:

> reduce cognitive load from email by filtering noise, highlighting action, and assisting execution

MailMind should answer:

- what requires my attention?
- what requires my action?
- what could benefit me if I act?

## Capability Model

### Email Ingestion

- fetch emails
- normalize emails
- store structured email records

### Email Understanding

Each email should be evaluated by:

- category
- actionability
- impact
- priority
- reasoning

### Email Querying

Conversational retrieval examples:

- what emails today?
- show job emails
- important emails
- emails from X

Preferred output groups:

- Action Required
- High Impact
- Informational

### Email Summarization

- daily summary
- grouped summary
- individual email summary

### Response Drafting

- generate draft replies
- adapt tone
- include context

### Approval-Gated Email Sending

Rules:

- no auto-send
- always require explicit approval

### Notification

Trigger when:

- `requires_action == true`
- or impact is high

### Memory Integration

Write:

- episodic memory
- error memory
- user decisions

Read:

- past interactions
- preferences

## Summary

MailMind is:

- WhatsApp-first
- decision-centric
- tool-driven
- approval-based

Flow:

`Read -> Decide -> Draft -> Approve -> Execute`
