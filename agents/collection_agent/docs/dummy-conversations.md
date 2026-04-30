# Dummy Conversations (Showcase Script)

Use these conversations for demo day.

## Conversation A: Strict Collections -> Pay By Phone

1. Customer (SMS): `contact_attempt case_id=COLL-1001 channel=sms reached=false`
2. Agent: Reminder sent. If customer can pay now, proceed to phone payment.
3. Customer: `I am willing to make a payment now for COLL-1001 amount=6000`
4. Agent: Runs `pay_by_phone_collect` in strict mode.
5. Agent response: payment success/receipt.

What this demonstrates:
- script-first collections behavior
- no LLM-style free drift
- deterministic payment capture path

## Conversation B: Hardship + Plan Proposal Loop + Channel Switch

1. Customer (SMS): `I need assistance. I lost my job and cannot pay this month. case_id=COLL-1002`
2. Agent: switches to hardship mode, runs `offer_eligibility`.
3. Plan node: injects `plan_propose` and returns initial plan.
4. Customer: `This does not work. Can you keep it under 1200?`
5. Plan node loop: revises and runs `plan_propose` again.
6. Customer: `switch to voice case_id=COLL-1002`
7. Agent: runs `channel_switch`, carries historical context.
8. Customer: `Yes that works for me`
9. Agent: captures promise (`promise_capture`) -> schedules followup (`followup_schedule`) -> updates disposition.

What this demonstrates:
- multi-step hardship negotiation
- plan revision loop
- SMS -> voice continuity
- workflow completion + audit/disposition

## Conversation C: Off-topic Guardrail

1. Customer: `Who won the super bowl last year?`
2. Agent: rejects and redirects to debt/payment domain.

What this demonstrates:
- compliance-safe scope boundaries

## Notes for Presenter

- Use same `--session-id` for all turns in one conversation so memory carries over.
- Show runtime files under `runtime/` after each flow to prove persistence.
