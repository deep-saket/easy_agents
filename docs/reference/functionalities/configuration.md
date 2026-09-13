# Configuration

Status: core YAML/environment behavior verified; one checked-in dotenv test is stale.

## Settings Model

`AppSettings` groups configuration into:

- `paths`
- `runtime`
- `notifications`
- `viewer`
- `llm`
- `planner`
- `memory`
- `integrations`

## Precedence

`AppSettings.from_env()` applies values in this order:

1. load repository/current-directory `.env` values into variables that are not already set
2. load the YAML file selected by `EASY_AGENT_CONFIG_PATH`
3. overlay recognized process environment variables
4. validate the merged settings with Pydantic

An already-set process variable wins over the same key in `.env` because the dotenv loader uses `setdefault`.

## Start from the Example

```bash
cp .env.example .env
```

The checked-in [`.env.example`](../../../.env.example) uses the names currently read by `AppSettings` and the concrete MailMind entrypoint. Its default runtime/source/channel settings are local or fake. Add only the credentials needed by the integration you enable.

## Important Variable Groups

| Area | Variables |
| --- | --- |
| Config file | `EASY_AGENT_CONFIG_PATH` |
| Paths | `EASY_AGENT_DB_PATH`, `EASY_AGENT_LOG_PATH`, `EASY_AGENT_POLICY_PATH`, memory/table/catalog paths |
| Runtime | `EASY_AGENT_SOURCE`, `EASY_AGENT_CLASSIFIER_MODE`, `EASY_AGENT_LLM_ENABLED`, `EASY_AGENT_POLL_SECONDS` |
| Default LLM | `EASY_AGENT_LLM_PROVIDER`, `EASY_AGENT_LLM_MODEL_NAME`, device, dtype, token, and thinking settings |
| Planner | `EASY_AGENT_PLANNER_ENABLED` plus provider/model/device/dtype/token settings |
| Memory | `EASY_AGENT_MEMORY_*` cache, archive, similarity, embedding, hybrid, and top-k settings |
| WhatsApp | `EASY_AGENT_WHATSAPP_MODE`, allowlist, destination, `EASY_AGENT_TWILIO_WHATSAPP_FROM` |
| Twilio credentials | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` |
| Gmail | `EASY_AGENT_GMAIL_CLIENT_ID`, secret, credentials path, and token path |
| Hosted models | `OPENAI_API_KEY`, `GROQ_API_KEY`, `NVIDIA_API_KEY`, `OLLAMA_API_KEY` as required |
| Generic endpoints | `EASY_AGENT_LLM_ENDPOINT_URL`, `EASY_AGENT_LLM_BASE_URL`, `EASY_AGENT_LLM_API_KEY` |

Collection Agent additionally reads its own `config.yml`, CLI overrides, and a package-local `.env`. Voice settings live in its YAML rather than `AppSettings`.

## Verification

Three core configuration tests passed for YAML loading, environment override precedence, and memory-vector settings. Copying the corrected `.env.example` into an isolated temporary directory and loading it through `AppSettings.from_env()` also passed.

`tests/test_dotenv_loading.py` still fails because it writes `EASY_AGENT_TWILIO_ACCOUNT_SID` and `EASY_AGENT_TWILIO_AUTH_TOKEN`, while the runtime intentionally reads the standard Twilio names `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`. The checked-in example now follows the runtime names.

## Safety

- `.env` is gitignored; verify that any agent-local `.env` is also ignored before using it.
- Never commit OAuth tokens, provider keys, customer records, or production runtime databases.
- Empty values for integer settings are invalid; omit/comment an optional integer instead of writing `NAME=`.
- Prefer a separate local YAML such as `config/*.local.yaml`, which is ignored by the repository.
