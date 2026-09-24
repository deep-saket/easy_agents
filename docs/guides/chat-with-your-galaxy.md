# Chat with Your Galaxy

Status: implemented local Control Room interface

The Control Room includes a Chat mode for sending conversational Missions into
the system. A message is processed server-side; the browser never calls the
model service or receives its optional API key.

## Start the dependencies

Mac Gemma remains hosted by the separate Foundation Mac Serving repository:

```bash
cd /Users/saketm10/Projects/foundation-ai-platform/mac-serving
.venv/bin/mac-serve serve
```

Then start this repository's Control Room:

```bash
cd /Users/saketm10/Projects/openclaw_agents
./run/constellation.sh
```

Open `http://127.0.0.1:8030`, select **Chat**, enter a message, and press Enter
or **Send through Wormhole**. Shift+Enter inserts a new line.

## What happens to a message

```text
Chat Portal
    ↓
Wormhole
    ↓
Personal Agent Galaxy
    ↓
Selected Circle
    ↓
Selected Rocky or Giant Planet
    ↓
Policy and Playbook evaluation
    ↓
Mac Gemma Rogue Star
    ↓
Answer + traceable route
```

The direct routing contract remains
`Wormhole → Galaxy → Circle → Planet`. The interface separately shows:

- Constellations containing the selected Circle and Planet. They are connected
  graph overlays, not mandatory routing hops.
- Satellites declared by the Planet's Charter. They are available tools, not
  agents. The UI explicitly distinguishes availability from actual invocation.
- Rogue Stars used for external resources. Mac Gemma is displayed outside
  Galaxy ownership even though the selected Planet is authorized to access it.

The current chat execution uses model reasoning only. It does not claim that a
Satellite ran. Future tool-aware execution can populate `invoked_satellites`
after the existing Satellite authorization and technical executor complete a
real call.

## Conversations and memory

The browser retains the current `conversation_id` and sends it with later
messages. The server provides up to eight recent turns as bounded completion
context and retains at most 20 turns per conversation and 128 conversations.

This history is intentionally process-local and ephemeral. Restarting the
Control Room clears it. It is not a Vault and should not be treated as durable
personal memory. Durable conversation storage requires explicit Vault scope,
retention, deletion, export, and redaction policy.

Use **New conversation** to discard the browser's current conversation ID and
start without previous-turn context.

## HTTP contract

Send a message:

```bash
curl -sS http://127.0.0.1:8030/api/v2/wormhole/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"calculate a satellite RF link budget"}'
```

Continue the same conversation by passing the returned identifier:

```json
{
  "message": "What assumption should I validate first?",
  "conversation_id": "chat-..."
}
```

The response contains the answer, Mission status, canonical `Trajectory`,
route context, available and invoked Satellites, the external model used, and a
compatibility visualization route for highlighting the existing Map.

## Failure behavior

- If Mac Gemma is not ready, the API returns HTTP 503 and the UI displays the
  dependency error without inventing an answer.
- Invalid or unroutable messages return HTTP 400.
- Model/runtime failures return a failed Mission answer and remain visible in
  Live and Replay observability views.
- Chat does not enable network access or external side effects. It submits a
  read-only advisory Mission and remains subject to the selected Planet's
  Charter and Gates. Words such as “call” or “buy” influence routing and the
  requested plan but do not grant permission to perform those actions.

The server should remain bound to loopback until authentication, per-principal
Galaxy authorization, and request-rate controls are implemented.
