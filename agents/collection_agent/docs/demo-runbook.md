# Demo Runbook

## Start interactive mode

```bash
python3 -m agents.collection_agent.main --interactive --session-id demo-1
```

## Suggested command sequence

```text
contact_attempt case_id=COLL-1001 channel=sms reached=false
I am willing to make a payment now for COLL-1001 amount=6000
I need assistance. I lost my job and cannot pay this month. case_id=COLL-1002
This does not work. Can you keep it under 1200?
switch to voice case_id=COLL-1002
Yes that works for me
Who won the super bowl last year?
```

## Reset between demos

- Clear `agents/collection_agent/runtime/*.json`
- Keep `conversation_states.json` as `{}` and `conversation_messages.json` as `{}`
