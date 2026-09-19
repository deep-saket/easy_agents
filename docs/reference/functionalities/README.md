# Functionality Catalog and Verification Matrix

This catalog documents each implemented functional area separately and records how it was verified on branch `saket/framework_update` on 2026-09-20.

The status labels mean:

- **Verified:** the applicable isolated tests and smoke checks passed.
- **Partially verified:** important paths passed, but the area's regression suite still has failures.
- **Externally unverified:** local contracts were tested, but a live third-party service was deliberately not called.
- **Placeholder:** there is no runnable implementation to test.

## Results at a Glance

| Functionality | Status | Evidence |
| --- | --- | --- |
| [Agent runtime and reusable nodes](./agent-runtime-and-nodes.md) | Verified | 16 focused tests passed; `GraphAgent`, `ApprovalNode`, `RouterNode`, and trace smokes passed |
| [Tools and execution](./tools.md) | Verified for shared tools; collection tools partial | 13 shared-tool/source tests passed; registry/catalog/executor smoke passed; collection suite is mixed |
| [Memory and retrieval](./memory.md) | Verified | 13 storage/type/vector tests passed, plus 9 memory-node tests in the runtime group |
| [Model adapters](./models.md) | Partially verified | 26 local/model-contract tests and one opt-in Mac Gemma live smoke passed; five remote adapters passed an isolated transport smoke; seven checked-in remote regression tests failed |
| [Channels, sources, and voice](./channels-and-voice.md) | Verified locally; live services unverified | 21 channel/voice tests passed; six fake-backed Gmail tool tests passed |
| [Observability](./observability.md) | Smoke verified | `GraphAgent` emitted turn and node events through an in-memory trace sink; tool tracing is exercised by agent tests |
| [Graph Builder](./graph-builder.md) | Verified | Five API tests and the `/health` smoke passed |
| [Configuration](./configuration.md) | Partially verified | Four config tests and the corrected `.env.example` load passed; one stale dotenv naming test failed |
| [Concrete agents](./agents.md) | Mixed | Simple, MailMind, Conversation Manager, and two specialist smokes passed; Collection Agent had 117 passes and 22 failures |
| [Constellation feature intake](./constellation-feature-intake.md) | Verified first slice | Fourteen focused offline tests passed for Roster validation, lifecycle filtering, all four decisions, risk/network gates, determinism, and the local API |

Focused counts overlap because some tests validate more than one capability. Do not add the rows to derive the repository total.

## Broad Test Run Excluding the Explicit Live Test

The repository collected 284 tests. The explicitly live Groq connectivity test was excluded because it uses a configured account and the network:

```bash
python -m pytest -q --ignore=tests/test_groq_connectivity.py
```

Result:

```text
253 passed, 1 skipped, 30 failed
```

The 30 failures were distributed as follows:

| Area | Failed | What failed |
| --- | ---: | --- |
| Collection Agent | 22 | plan transitions, response constraints, discount/hardship routing, callback routing, promise-date extraction, and required-entity fallback |
| Remote model regression tests | 7 | test doubles no longer match the current TLS/SDK transport implementation; despite excluding the explicit live test, the Groq unit path attempted external authentication |
| Dotenv regression test | 1 | the test expects `EASY_AGENT_TWILIO_ACCOUNT_SID` while runtime code uses `TWILIO_ACCOUNT_SID` |

This is not yet a hermetic or network-safe default suite: the remote Groq regression path observed ambient credentials and attempted external authentication. No production claim should be based only on the total pass percentage. Read the individual functionality page and the failing test names before relying on a path.

## Live Checks Not Performed

The following were not invoked because testing them would require credentials, network access, a live account, large model downloads, hardware, or an externally visible side effect:

- the Groq streaming connectivity test
- real OpenAI, Groq, NVIDIA, or remote Ollama inference
- real Gmail OAuth fetch or send
- real Twilio WhatsApp or voice delivery
- live Pipecat media sessions
- downloading and loading full Qwen, FunctionGemma, Whisper, SpeechT5, or speaker-embedding weights
- browser-driven end-to-end interaction with the Collection Agent UI

Their adapters were tested with fakes where the repository provides them. A live integration must be verified in a dedicated non-production account with explicit authorization.

## Reproduction Commands

Run from the repository root after activating `.venv`:

```bash
# Framework runtime and nodes
python -m pytest -q \
  tests/test_agent_node.py tests/test_intent_node.py tests/test_react_node.py \
  tests/test_reflect_node.py tests/test_memory_node.py tests/test_memory_retrieve_node.py

# Shared tools and fake-backed email behavior
python -m pytest -q \
  tests/test_math_tools.py tests/test_classifier.py tests/test_gmail_source.py \
  tests/test_gmail_tools_real.py tests/test_mailmind_summary_tool.py \
  tests/test_memory_search_tool.py

# Memory
python -m pytest -q \
  tests/test_memory_system.py tests/test_memory_types.py tests/test_vector_retrieval.py

# Local/model contracts that make no provider request
python -m pytest -q \
  tests/test_function_gemma_limits.py tests/test_huggingface_json.py \
  tests/test_llm_classifier.py tests/test_llm_singleton.py tests/test_local_llm.py \
  tests/test_mac_gemma.py

# Channels and voice contracts with fakes
python -m pytest -q \
  tests/test_whatsapp_endpoint.py tests/test_whatsapp_interface.py \
  tests/test_whatsapp_node.py tests/test_pipecat_runner.py \
  tests/test_speech_tts_config.py tests/test_voice_backend_config.py \
  tests/test_voice_processing_pipeline.py

# Graph Builder
python -m pytest -q tests/test_graph_builder_api.py

# MailMind
python -m pytest -q \
  tests/test_mailmind_agent.py tests/test_mailmind_nodes.py \
  tests/test_mailmind_summary_tool.py tests/test_classifier.py \
  tests/test_gmail_source.py tests/test_gmail_tools_real.py

# Conversation Manager
python -m pytest -q \
  tests/test_conversation_manager_agent.py tests/test_conversation_manager_runtime.py
```

## Interpreting the Evidence

A passing test verifies the inputs, outputs, and failure cases asserted by that test. It does not establish load capacity, data privacy, reliability against a real provider, or suitability for production. The current repository is best treated as an experimental local-first framework with several strong components and one large domain prototype.
