# Refactor Fix Plan

This repository was migrated from a MailMind-specific package layout to a shared multi-agent platform layout.

This plan records the main refactor stages that were needed to make the repository internally consistent again.

## Goal

Make the repository runnable and coherent under the shared platform-first layout.

## Key Completed Areas

- removed remaining `src.mailmind.*` dependencies from shared runtime code
- repaired packaging metadata and package naming
- restored shared schemas, storage, interfaces, and config ownership under `src/`
- preserved concrete agents under `agents/`
- rebuilt MailMind as a thin domain layer on top of shared framework primitives

## Remaining Cleanup Themes

- reduce legacy naming drift
- continue test cleanup where older assumptions remain
- keep agent-specific logic out of shared platform code unless intentionally reusable

## Principle

Shared platform code should depend only on shared modules in `src/`.

Agent-specific code should live under the relevant agent package in `agents/`.
