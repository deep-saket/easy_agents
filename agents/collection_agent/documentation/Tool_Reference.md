# Tool Reference

This reference explains how each tool should be called and how output should be interpreted inside the graph.

## Tool Rules

- Inputs should match schema exactly (typed fields, required IDs).
- Tool failures must not silently progress customer-owned plan steps.
- Tool output should be added to `observation.tool_phase.output` and consumed by `plan_proposal` + `relevant_response`.

## Tools

### `case_fetch`

- Purpose: fetch delinquent case snapshot for one borrower/case/portfolio.
- Inputs: `case_id?`, `customer_id?`, `portfolio_id?`
- Outputs: `total`, `cases[]`
- Use when: call initialization, case validation, context re-sync.

### `case_prioritize`

- Purpose: rank high-risk/high-recovery cases.
- Inputs: `case_ids?`, `portfolio_id?`
- Outputs: `total`, `queue[]`

### `contact_attempt`

- Purpose: log outreach attempts with channel/reach result.
- Inputs: `case_id`, `channel?`, `reached?`
- Outputs: `attempt_id`, `status`

### `customer_verify`

- Purpose: verify borrower identity against challenge answers.
- Inputs: `case_id?`, `customer_id?`, `challenge_answers?`
- Outputs: `status` (`verified|failed|locked`), `failed_attempts`, `required_fields`
- Important:
  - `verify_identity` plan step completes only when `status=verified`.
  - partial natural-language identity utterances are tracked in memory but do not complete the step.

### `loan_policy_lookup`

- Purpose: load policy constraints for waiver/restructure promises.
- Inputs: `case_id?`, `loan_id?`
- Outputs: policy object

### `dues_explain_build`

- Purpose: build borrower-safe dues explanation text.
- Inputs: `case_id`
- Outputs: `total_due`, `explanation`

### `offer_eligibility`

- Purpose: evaluate concession eligibility.
- Inputs: `case_id`, `hardship_flag?`, `requested_waiver_pct?`
- Outputs: `allowed`, `offer_type`, `approved_waiver_pct`

### `plan_propose`

- Purpose: propose/revise EMI plan under hardship context.
- Inputs: `case_id`, `hardship_reason?`, `revision_index?`, `max_installment_amount?`
- Outputs: `plan_id`, `monthly_amount`, `first_due_date`, `status`

### `payment_link_create`

- Purpose: issue pay-now link.
- Inputs: `case_id`, `amount`, `channel?`
- Outputs: `payment_reference_id`, `payment_url`, `expires_at`

### `pay_by_phone_collect`

- Purpose: simulate assisted phone payment.
- Inputs: `case_id`, `amount`, `consent_confirmed?`
- Outputs: `payment_id`, `status`, `receipt_reference`

### `payment_status_check`

- Purpose: reconcile payment state.
- Inputs: `payment_reference_id`
- Outputs: `status`, `needs_additional_action`

### `promise_capture`

- Purpose: record promise-to-pay details.
- Inputs: `case_id`, `promised_date`, `promised_amount`
- Outputs: `promise_id`, `status`

### `followup_schedule`

- Purpose: schedule next callback/reminder.
- Inputs: `case_id`, `scheduled_for`, `preferred_channel?`
- Outputs: `schedule_id`

### `disposition_update`

- Purpose: persist final disposition + audit note.
- Inputs: `case_id`, `disposition_code`, `notes`
- Outputs: `audit_id`, `updated_at`

### `channel_switch`

- Purpose: move conversation to another channel while preserving context.
- Inputs: `case_id`, `from_channel?`, `to_channel?`
- Outputs: `switch_id`, `carried_context_summary`

### `human_escalation`

- Purpose: escalate dispute/fraud/sensitive requests to humans.
- Inputs: `case_id`, `reason`
- Outputs: `escalation_id`, `queue`, `priority`
