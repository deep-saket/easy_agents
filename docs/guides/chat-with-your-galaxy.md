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

Chat can execute four local, account-free Satellites today:

| Satellite | Trigger examples | Effect |
| --- | --- | --- |
| Calculate | `Calculate 12 * (3 + 4)` | validated local compute |
| Unit Convert | `Convert 5 miles to km` | validated local compute |
| Memory Write | `Remember that my grocery day is Saturday` | durable local memory write |
| Memory Search | `What do you remember about grocery day?` | scoped local memory read |

These calls pass through the Planet Charter, canonical `SatelliteExecutor`,
shared `ToolExecutor`, schema validation, and observability events. Exact tool
evidence is authoritative for a tool-backed answer; unverified base-model
continuation is omitted instead of being mixed into the result. The UI marks
each local tool as `ready` and highlights only tools that actually ran.

The remaining declared Satellites—Gmail fetch, stored-email operations, reply
drafting, email send, and notification—are not enabled in Chat. Network or
external-send behavior still requires configured providers and explicit
approval; Chat never interprets ordinary prose as authorization for those
effects.

## Conversations and memory

The browser retains the current `conversation_id` and sends it with later
messages. The server provides up to eight recent turns as bounded completion
context and retains at most 20 turns per conversation and 128 conversations.
Conversation turns persist across Control Room restarts in
`data/galaxy_chat.db` by default. Set `EASY_AGENTS_DATA_DIR` to move all Galaxy
chat and memory data to another local directory.

Conversation history and long-term memory are deliberately separate. A normal
chat turn is retained only as bounded working context. Only an explicit
`Remember ...` command invokes Memory Write and creates a durable typed memory
record in `data/galaxy_memory.duckdb`; an explicit recall request invokes
Memory Search. This prevents every casual message from becoming permanent
memory without the user's intent.

Use **New conversation** to delete the current bounded server-side history,
discard the browser's conversation ID, and start without previous-turn context.

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
route context, available and invoked Satellites, validated invocation outputs,
`answer_source`, optional model `generation` evidence, and a compatibility
visualization route for highlighting the existing Map. `used_model` means a
model call occurred; `generation.output_used` says whether that generated text
actually appears in the final answer.

The Control Room renders the same distinction under **Answer provenance**. A
Satellite-backed calculation or memory result is labeled as a verified
Satellite answer and does not invoke Gemma. Open-ended advisory messages use
Gemma and expose their generation evidence separately.

Inspect truthful runtime readiness separately:

```bash
curl -sS http://127.0.0.1:8030/api/v2/readiness
```

The response distinguishes active and sandboxed Planets, advisory execution
from autonomous effects, locally executable Satellites from declared but
disabled integrations, Gemma readiness, the chat-history backend, and the
Commons readiness totals. The complete 30-component Commons audit is available
at `/api/v2/circles/commons/readiness`; see the
[Commons Circle runtime](../reference/functionalities/commons.md).

## Failure behavior

- If Mac Gemma is not ready, the API returns HTTP 503 and the UI displays the
  dependency error for model-backed requests without inventing an answer.
  Exact local Satellite requests continue to work without Gemma.
- Invalid or unroutable messages return HTTP 400.
- Model/runtime failures return a failed Mission answer and remain visible in
  Live and Replay observability views.
- A completed model request records finish reason, tokens when available,
  duration, final-output use, and basic output checks. `accepted` means those
  cheap checks passed; it is not a truthfulness or instruction-following score.
- Highly repetitive, too-short, control-character, or prompt-repeating model
  output is rejected and replaced with the selected Planet's deterministic
  bounded plan. The same applies to mechanically detectable violations of an
  explicit brevity, one-item, or one-to-three-sentence request. The failed
  evidence remains visible in the trace.
- Local compute and explicit memory tools can run. Chat does not enable network
  access or external side effects. Its Planet response remains advisory and is
  subject to the selected Charter and Gates. Words such as “call” or “buy”
  influence routing and the requested plan but do not grant permission to
  perform those actions.

The server should remain bound to loopback until authentication, per-principal
Galaxy authorization, and request-rate controls are implemented.
