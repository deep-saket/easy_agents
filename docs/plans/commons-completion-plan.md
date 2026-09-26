# Commons Completion Plan

Status: local foundation complete; external integration phases remain gated

This plan tracks the reusable services needed by every Circle. It separates
local state management—which can be implemented and tested safely—from actions
that require an authenticated provider, a human decision, and idempotent
resumption.

## Completed local foundation

- [x] One durable SQLite Commons runtime shared by the API and Chat Satellites.
- [x] Six named Vault boundaries with lifecycle state, isolated reads/writes,
  export, record deletion, and exact-confirmation purge.
- [x] Chat Vault selection with Charter-aware Planet routing.
- [x] Immutable artifact versions, checksums, latest-version lookup, and soft
  deletion.
- [x] Explicit local knowledge ingestion, bounded lexical search, stable
  citation identifiers, extractive summaries, and clearly labeled lexical
  claim-support checks.
- [x] Durable one-time/recurring Scheduled Reviews, due claiming, completion,
  cancellation, and a local background due monitor.
- [x] Durable approval decisions with bounded resume context and exactly-once
  decision semantics.
- [x] Local calendar proposal inspection and decisions without provider I/O.
- [x] Typed HTTP APIs, Control Room Commons UI, redacted operational events,
  readiness evidence, docstrings, documentation, and integration tests.

## Phase 1: stronger local reasoning

1. Add versioned rubric contracts for Adversarial Review.
2. Run deterministic structure/evidence checks before optional model critique.
3. Store each review as an Artifact version linked to source citations.
4. Add contradiction, missing-evidence, and stale-source test fixtures.

Exit criteria: a review names its rubric version, input artifacts, evidence
sources, findings, and unresolved claims; rerunning the same deterministic
checks produces the same result.

## Phase 2: Research with Provenance

1. Define a source-adapter protocol with authentication, allow-listed domains,
  rate limits, and fetch timestamps.
2. Implement one read-only primary-source adapter first.
3. Preserve retrieved content, checksum, URI, publication metadata, and access
  time as a Knowledge Source or Artifact.
4. Keep model summaries downstream of retrieval and retain sentence-to-source
  attribution.

Exit criteria: every externally sourced assertion links to retained source
evidence, and disabling the connector leaves all local knowledge functions
operational.

## Phase 3: multi-Planet synthesis

1. Allow Chat to request a bounded Crew size.
2. Give every Work Order a shared Mission budget and narrowed Permission Grant.
3. Require structured Planet results with claim/evidence separation.
4. Synthesize only after all required results are terminal or the budget ends.
5. Trace disagreements instead of silently merging them.

Exit criteria: Route & Synthesize is end-to-end operational in Chat with
deterministic budget, timeout, partial-result, and disagreement tests.

## Phase 4: provider actions after approval

1. Add a provider-worker protocol that consumes an approved record by ID.
2. Require authentication, per-principal Galaxy authorization, idempotency key,
  expiry, and payload checksum before execution.
3. Atomically claim the approval so only one worker can execute it.
4. Persist the provider result and terminal effect state without erasing the
  original approval context.
5. Start with a calendar sandbox; keep email, purchases, and calls disabled
  until their provider-specific failure and rollback behavior is tested.

Exit criteria: duplicate worker delivery cannot repeat an effect; expired,
changed, rejected, or unauthorized records cannot execute; every attempt is
visible in Live and Replay.

## Phase 5: deployment hardening

1. Add authentication and per-user Galaxy/Vault authorization.
2. Encrypt sensitive Vault data at rest with an external key boundary.
3. Add backup, restore, schema migration, retention, and purge verification.
4. Add request/body limits, rate limiting, CSRF protection, and audit export.
5. Add load, crash-recovery, concurrent-write, and corruption-recovery tests.

The Control Room should remain bound to `127.0.0.1` until this phase is
complete.
