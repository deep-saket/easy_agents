# Missing Data / Integration Requirements

This file documents tool capabilities that are intentionally not fully implemented in offline mode because they require production-grade data or external systems.

## Tools Deferred From Full Implementation

1. `negotiation_agent_tool`
- Why deferred: needs historical call transcripts, outcome labels, and policy exception examples.
- Required inputs:
- transcript dataset with borrower objections and final outcomes
- policy rulebook with approval/denial rationale
- target KPI definitions (PTP kept rate, conversion targets)
- Suggested implementation path:
- start with rule templates + objection taxonomy
- then add model-based next-best-action ranking

2. `qa_review_agent_tool`
- Why deferred: needs compliance rubric and annotated quality dataset.
- Required inputs:
- call/chat transcripts with human QA scores
- regulatory compliance checklist and prohibited-phrase lists
- severity definitions for violations
- Suggested implementation path:
- deterministic rule pass for hard compliance checks
- scorecard model for soft-quality checks

3. `dispute_triage_agent_tool`
- Why deferred: needs dispute taxonomy and downstream queue mapping from ops.
- Required inputs:
- dispute type definitions (service, fraud, legal, billing, etc.)
- historical dispute tickets with final resolution labels
- queue routing ownership and SLA matrix
- Suggested implementation path:
- keyword/rule baseline first
- train or prompt-tune classifier from labeled tickets

## Partially Mocked Integrations

1. `payment_link_create`
- Current mode: generates deterministic mock links (`payments.example.local`).
- Production requirements:
- payment gateway credentials
- signed URL service
- callback webhook pipeline

2. `payment_status_check`
- Current mode: reads local runtime state and optional `simulate_status` override.
- Production requirements:
- transaction status API integration
- reconciliation event stream

## Data Contracts Needed To Move To Production

- borrower master profile data (with masking strategy)
- delinquency feed and portfolio segmentation
- loan-level policy tables and eligibility flags
- outbound channel delivery logs
- follow-up scheduler API and callback events
- disposition and audit sink schema accepted by operations
