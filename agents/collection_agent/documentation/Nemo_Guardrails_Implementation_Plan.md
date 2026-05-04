# NeMo Guardrails Implementation Plan

## Objective

Add guardrails around the existing Collection Agent graph without changing the core graph architecture.

The goal is to keep the current node/tool flow but enforce:

1. scope control,
2. identity/verification gating,
3. safe payment-link behavior,
4. PII-safe responses/logging,
5. compliant collections tone,
6. action-step consistency with plan markers,
7. escalation paths for trust/safety concerns.

## Current Integration Boundary

Guardrails should wrap three points:

1. **Input guardrails**: before intent routing.
2. **Action guardrails**: before tool execution and before plan step advancement.
3. **Output guardrails**: before response leaves `response` node.

This preserves existing nodes:

- `relevance_intent`
- `pre_plan_intent`
- `execution_path_intent`
- `plan_proposal`
- `react`
- `tool_execution`
- `reflect`
- `relevant_response`

## Proposed Folder Layout

Create a new folder under the collection agent:

```text
agents/collection_agent/guardrails/
  README.md
  config/
    rails.yaml
    prompts.yml
  validators/
    scope.py
    verification.py
    payment_link.py
    pii_masking.py
    conduct.py
    step_consistency.py
    escalation.py
  integration/
    pre_input.py
    pre_tool.py
    post_output.py
```

## Guardrail Set (Phase 1)

### 1) Scope Guardrail

Purpose:

- Keep conversation inside collections domain.
- Avoid false “out-of-scope” for short in-session replies.

Policy:

- Allow: dues, EMI, payment, verification, hardship, settlement, follow-up, scam/trust verification.
- Block/redirect: unrelated general topics.

Action:

- Return a polite scope response with one-line redirection to collections flow.

### 2) Verification Gate Guardrail

Purpose:

- Prevent dues details, policy decisions, or payment actions before required identity fields are complete.

Policy:

- Required fields from state: `active_verification_required_fields`.
- Completion status from state: `verification_collected`, `identity_verified`.

Action:

- If incomplete: response can request only missing fields.
- If complete: allow progression to dues/payment stages.

### 3) Payment Link Guardrail

Purpose:

- Ensure payment links are only sent from approved domains/templates.

Policy:

- Link host must match whitelist from config.
- Message cannot contain ad-hoc unknown URLs.

Action:

- Reject unsafe links.
- Replace with safe fallback: ask customer to use official channel.

### 4) PII Protection Guardrail

Purpose:

- Prevent leakage of sensitive values in responses and logs.

Policy:

- Mask PAN/account numbers except minimal suffix policy.
- Never echo full DOB + full PAN/account in one response.

Action:

- Apply masking transform before UI output and trace write.

### 5) Conduct/Compliance Guardrail

Purpose:

- Enforce compliant debt-collection tone.

Policy:

- No threats, coercion, harassment, legal bluffing, or abusive language.

Action:

- Rewrite or block with compliant alternative.

### 6) Plan Step Consistency Guardrail

Purpose:

- Prevent plan tree from skipping required predecessor steps without explicit marker transition.

Policy:

- Node can move to child only if parent marked `done` or `skipped`.
- `verify_identity` cannot be marked `done` when `identity_verified=false`.

Action:

- Reject invalid transition.
- Force `plan_proposal` to revise step update.

### 7) Escalation Guardrail

Purpose:

- Handle repeated dispute/scam concern/confusion.

Policy:

- If concern repeats >= configured threshold within rolling turns, escalate.

Action:

- Route output to callback verification/human handoff instruction.

## State Keys to Add (Minimal)

Recommended graph state additions:

- `guardrail_events`: list of guardrail decisions per turn.
- `guardrail_flags`: active boolean flags (`verification_block`, `scope_redirect`, etc.).
- `risk_signals`: counters for scam concern, abuse, repeated refusal.
- `escalation_status`: none|suggested|triggered.

These keys are additive and do not change existing state contracts.

## Runtime Integration Points

### Pre-Input

Where:

- Before relevance intent classification.

What:

- scope and safety pre-check.

### Pre-Tool / Pre-Plan-Transition

Where:

- Before tool execution in `tool_execution`.
- Before applying plan tree step updates in `plan_proposal`.

What:

- verification gate,
- step consistency,
- payment-link constraints for tool outputs.

### Post-Output

Where:

- Immediately before final response leaves `relevant_response`.

What:

- PII masking,
- compliance tone check,
- final target validation.

## Metrics (for eval and demo)

Track per run:

- `guardrail_trigger_count`
- `verification_block_count`
- `unsafe_link_block_count`
- `scope_redirect_count`
- `compliance_rewrite_count`
- `escalation_trigger_count`

Store in runtime eval artifacts for prompt/behavior audits.

## Rollout Plan

### Step 1

- Add `guardrails/` skeleton and config files.
- Wire no-op integration hooks in pre-input/pre-tool/post-output paths.

### Step 2

- Implement deterministic validators for:
  - verification gate,
  - step consistency,
  - payment link whitelist,
  - PII masking.

### Step 3

- Add LLM-backed moderation/rewrite policies for:
  - scope edge cases,
  - compliance tone.

### Step 4

- Add escalation logic and thresholds.
- Add dashboard counters in UI right panel.

### Step 5

- Run scripted evals and update prompts based on trigger logs.

## Non-Goals (for this phase)

- No core graph rewrite.
- No replacement of current intent node architecture.
- No external policy engine dependency beyond NeMo Guardrails integration.

## Acceptance Criteria

1. Customer cannot receive dues/payment instructions without verification completion.
2. Unsafe payment links are never sent.
3. Out-of-scope responses are redirected without breaking active session continuity.
4. Response text is masked and compliant.
5. Plan-tree transitions respect step markers.
6. Guardrail decisions are visible in runtime state/events for debugging.
