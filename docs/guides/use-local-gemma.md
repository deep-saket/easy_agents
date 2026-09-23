# Use the Mac-Hosted Gemma Model

Status: implemented and live-smoke verified

Contract version: `1.0.0`

The framework calls the native Apple Silicon Gemma service as an external
inference dependency. Model weights, llama.cpp, process ownership, and serving
configuration stay in
`/Users/saketm10/Projects/foundation-ai-platform/mac-serving`. This repository
does not vendor, import, or modify that serving repository; it uses only the
loopback HTTP contract below.

## Service contract

| Property | Value |
| --- | --- |
| Default base URL | `http://127.0.0.1:8080` |
| Model | `gemma-4-E4B` |
| Readiness | `GET /readyz` |
| Discovery | `GET /v1/models` |
| Inference | `POST /v1/completions` |
| Serving context | 16,384 prompt-plus-output tokens per slot |
| Optional key | `MAC_SERVING_API_KEY` |

Do not use `/v1/chat/completions`. The deployment is the pretrained
`google/gemma-4-E4B` base model, not an instruction-tuned chat model.

## Check the service

After an editable install:

```bash
local-gemma ready
local-gemma models
```

From a checkout without installing the command:

```bash
PYTHONPATH=src python -m src.llm.mac_gemma_cli ready
PYTHONPATH=src python -m src.llm.mac_gemma_cli models
```

Expected model discovery includes `gemma-4-E4B`.

If readiness fails, start the separately managed service:

```bash
cd /Users/saketm10/Projects/foundation-ai-platform/mac-serving
.venv/bin/mac-serve serve
```

The Easy Agents client never starts or exposes that persistent process.

## Generate a raw completion

```bash
local-gemma complete "The capital of India is" \
  --max-tokens 32 --temperature 0.2 --stop __END_NEVER__ --json
```

The JSON form reports text, finish reason, and portable token usage. This is a
base-model continuation: phrase prompts as text the model should continue. Do
not assume system/user chat semantics. The explicit sentinel stop avoids the
developer CLI's default blank-line stop, which may terminate a continuation
before useful Fleet content appears.

## Python API

```python
from src.llm import LLMFactory

llm = LLMFactory.build_mac_gemma_llm(
    max_new_tokens=128,
    temperature=0,
    top_p=0.95,
)

llm.require_ready()
print(llm.list_models())

result = llm.generate_result("A concise explanation of gradient descent:\n")
print(result.content)
print(result.total_tokens)
```

For compatibility with current agent nodes, two prompt arguments are joined
with one blank line:

```python
text = llm.generate(
    "Continue the following task in JSON.",
    '{"task":"classify this message","result":',
)
```

No chat template is added.

## Environment configuration

The adapter reads:

```bash
EASY_AGENT_LLM_PROVIDER=mac_gemma
EASY_AGENT_LLM_MODEL_NAME=gemma-4-E4B
GEMMA_API_BASE=http://127.0.0.1:8080
# MAC_SERVING_API_KEY=only-if-the-service-requires-it
EASY_AGENT_LLM_MAX_NEW_TOKENS=256
EASY_AGENT_LLM_TIMEOUT_SECONDS=300
EASY_AGENT_LLM_TEMPERATURE=0.2
EASY_AGENT_LLM_TOP_P=0.95
```

The optional key is read at runtime, omitted when empty, hidden from the client
representation, and redacted from bounded error diagnostics. Never put a real
key in committed YAML, `.env.example`, tests, prompts, or trace output.

## Use with current agents

The Specialist Fleet and Control Room expose two per-Mission choices:

- `mac_gemma`: calls the external service after a readiness check;
- `none`: builds a deterministic policy-aware plan without inference.

In the Control Room, select a Specialist and choose **Mac Gemma · external
local service**. The UI displays readiness from
`GET /api/models/mac-gemma/status` and sends `model_id: "mac_gemma"` only to
the Easy Agents server. It never puts `MAC_SERVING_API_KEY` in browser code.

The Fleet profile defaults to 256 output tokens, temperature `0.2`, top-p
`0.95`, and no blank-line stop. Empty model output is treated as a failed Run,
not a completed Mission.

Because `gemma-4-E4B` is a pretrained completion model, the Fleet sends it a
short Specialist-labelled document continuation instead of the longer
instruction/chat prompt used by other adapters. Routing, memory boundaries,
policy checks, approval Gates, and effect permissions are enforced before the
model call; the generated advisory text is marked unverified in the result.

MailMind accepts the shared environment configuration above.

Collection Agent uses its own YAML. For an experiment, change its `llm` block:

```yaml
llm:
  enabled: true
  provider: mac_gemma
  model_name: gemma-4-E4B
  base_url: http://127.0.0.1:8080
  max_new_tokens: 256
  temperature: 0
  top_p: 0.95
  timeout_seconds: 300
```

Do not make this the default for a strict structured-output workflow until its
task-specific evaluations pass. MailMind and Collection Agent were originally
prompted for instruction/chat models; a pretrained base model may continue the
prompt fluently without following the requested JSON or policy format.

## Model-development workflow

The serving API performs inference only. It does not fine-tune, train, merge,
quantize, or publish model weights. Use it as a stable development dependency
for:

1. recording a baseline on versioned prompts and evaluation datasets;
2. developing continuation and few-shot formats appropriate for a base model;
3. measuring output quality, latency, finish reasons, and token use;
4. generating candidate synthetic examples that are reviewed before training;
5. comparing a newly served checkpoint against the same locked evaluations;
6. validating agent behavior before promoting that model profile.

Keep datasets, expected outputs, scoring logic, and model-server versions under
separate version control. Never treat generated text as a verified training
label without review. Do not use private household, customer, credential, or
company data for training unless its consent, retention, and deletion policy is
explicit.

For structured agent development, build an evaluation set before changing the
default provider. At minimum measure:

- valid JSON/schema rate;
- task accuracy and refusal/abstention behavior;
- prompt-injection and secret-leakage cases;
- context-length and truncation behavior;
- latency and token usage;
- deterministic regression cases at temperature zero.

## Failure behavior

- `400`: invalid prompt or generation parameters; the bounded backend detail is
  surfaced.
- `401`: missing or invalid optional key; the key is never included in the
  error.
- `503`: backend not ready; completion requests retry only a bounded number of
  times.
- connection failure: bounded retry, then a diagnostic naming the local base
  URL.
- invalid response: explicit errors for missing `choices[0].text` or malformed
  JSON.

Readiness uses a short timeout. Generation uses the longer configured timeout.
The client currently uses non-streaming inference; add SSE streaming only for a
caller that can consume incremental output and cancellation correctly.

## Tests

Mocked contract and configuration tests make no network calls:

```bash
PYTHONPATH=src pytest -q tests/test_mac_gemma.py tests/test_config.py
```

The live smoke is opt-in and calls only the loopback service:

```bash
RUN_LOCAL_GEMMA_LIVE=1 PYTHONPATH=src \
  pytest -q tests/test_mac_gemma_live.py
```

The Fleet API tests inject a fake Gemma client; they never start or contact the
external serving repository. A real end-to-end check requires both services:

```bash
# Terminal 1: external serving repository
cd /Users/saketm10/Projects/foundation-ai-platform/mac-serving
.venv/bin/mac-serve serve

# Terminal 2: this repository
cd /Users/saketm10/Projects/openclaw_agents
./run/constellation.sh
```
