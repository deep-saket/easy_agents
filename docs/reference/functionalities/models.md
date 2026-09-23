# Model Adapters

Status: local contracts verified; hosted transports partially verified; live providers unverified.

## Supported Adapter Families

| Adapter | Intended backend | Network boundary |
| --- | --- | --- |
| `LocalLLM` | Wrapper around a local generation client | Offline after dependencies and weights are available |
| `Qwen3_1_7BLLM` | Hugging Face Qwen model | May download weights on first use |
| `FunctionGemmaLLM` | FunctionGemma local planner | May download weights on first use |
| `MacGemmaLLM` | Native Apple Silicon `gemma-4-E4B` llama.cpp completions service | Loopback by default; optional local key |
| `EndpointLLM` / `RemoteLLM` | Arbitrary JSON text-generation endpoint | Depends on endpoint |
| `OpenAICompatibleLLM` | OpenAI-style chat-completions server, including local servers | Local or network, based on URL |
| `OpenAILLM` | Hosted OpenAI-compatible endpoint default | Network and API key |
| `NvidiaLLM` | NVIDIA Integrate API | Network and API key |
| `GroqLLM` | Groq SDK chat completions | Network and API key |

The common node-facing method is:

```python
text = llm.generate(system_prompt, user_prompt)
```

Some wrappers also provide `generate_json()` and `structured_generate()`.

## Local Usage

Install the optional dependencies:

```bash
python -m pip install -e ".[local-llm]"
```

Construct the checked-in default local wrapper:

```python
from src.llm import LLMFactory

llm = LLMFactory.build_default_local_llm(
    model_name="Qwen/Qwen3-1.7B",
    device_map="auto",
    torch_dtype="auto",
    enable_thinking=False,
)
```

This is only offline when the model files are already available locally. Resource requirements depend on the model, dtype, and device.

## OpenAI-Compatible Usage

```python
from src.llm import LLMFactory

llm = LLMFactory.build_openai_compatible_llm(
    base_url="http://127.0.0.1:11434",
    api_path="/v1/chat/completions",
    model_name="your-local-model",
)
```

Use the factory-specific builders for OpenAI, Groq, and NVIDIA. Load credentials from environment variables; do not hard-code or commit them.

## Mac-Hosted Gemma Usage

The native Mac service is a completions endpoint, not an OpenAI-compatible chat
endpoint:

```python
from src.llm import LLMFactory

llm = LLMFactory.build_mac_gemma_llm(max_new_tokens=128)
llm.require_ready()
result = llm.generate_result("A short explanation of gradient descent:\n")
print(result.content)
```

The adapter provides readiness, model discovery, non-streaming completion,
portable usage fields, bounded retry, credential redaction, JSON parsing, and
Pydantic validation. It reads `GEMMA_API_BASE` and the optional
`MAC_SERVING_API_KEY`.

The Specialist Fleet wraps this adapter in a reusable `mac_gemma` profile. The
profile points only at the documented loopback API in the separate Mac-serving
repository, disables the problematic blank-line stop for agent prompts, and is
selectable per Mission from the API, CLI, and Control Room. Routing, policy,
approval Gates, and external-effect authority remain deterministic.

The served `gemma-4-E4B` is a pretrained base model. Existing agents that rely
on instruction following or exact JSON require task-specific evaluation before
using this provider. See [Use the Mac-Hosted Gemma Model](../../guides/use-local-gemma.md).

## Verification

Twenty-six isolated tests passed for:

- FunctionGemma generation limits
- Hugging Face JSON repair and generation behavior
- `LocalLLM` prompt shaping and structured generation
- local-model singleton caching
- LLM classifier prompt and result mapping
- Mac Gemma completion payloads and portable response parsing
- readiness and model discovery
- environment/factory integration for MailMind and Collection Agent
- bounded retry, generation limits, and key redaction
- schema-aware structured-generation prompt construction

An explicitly enabled loopback live smoke passed readiness, discovery, and a
small completion against the running `gemma-4-E4B` service.

A no-network smoke replaced HTTP and Groq SDK transports with fakes and successfully exercised `EndpointLLM`, `OpenAICompatibleLLM`, `OpenAILLM`, `NvidiaLLM`, and `GroqLLM`.

The checked-in `tests/test_remote_llm.py` regression suite is currently red: seven tests failed. Six urllib-based tests use fakes that do not accept the implementation's TLS `context` argument. The Groq factory test still patches urllib even though `GroqLLM` now uses the Groq SDK, so it attempted provider authentication with the test key instead of remaining isolated.

The explicitly live Groq connectivity test was not run.

## Constraints

- Hosted provider behavior has not been verified in this documentation pass.
- The remote regression suite must be updated before CI can safely claim provider-adapter coverage.
- Model adapters do not yet expose one uniform capability description for context length, tool calling, streaming, or structured output.
- `MacGemmaLLM` is non-streaming and the service is inference-only; model training and checkpoint management remain outside this repository.
- Use deterministic rules for permissions, approvals, limits, and irreversible actions even when a model plans the workflow.
