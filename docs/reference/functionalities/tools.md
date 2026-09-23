# Satellites (Tools) and Execution

Status: shared tool framework verified; Collection Agent's domain tool flows are partially verified.

**Satellite** is the canonical Galaxy term for a callable tool. In the current
implementation, every Satellite is backed by the existing `BaseTool`,
`ToolRegistry`, and `ToolExecutor` contracts. Stable `tool:*` identifiers,
Python class names, and `tool.*` observability events remain unchanged during
the compatibility migration.

## Satellite Contract

Every `BaseTool` declares:

- unique `name`
- planner-facing `description`
- Pydantic `input_schema`
- Pydantic `output_schema`
- `execute(validated_input)` implementation

`ToolRegistry` stores tools and exports JSON- or YAML-serializable catalogs. `ToolExecutor` resolves a tool, validates raw input, runs it, validates output, saves a structured log, records a trace event, and optionally writes success/failure memory.

## Minimal Usage

```python
from src.tools import ToolExecutor, ToolRegistry
from src.tools.math import CalculateTool, UnitConvertTool

registry = ToolRegistry()
registry.register(CalculateTool())
registry.register(UnitConvertTool())

print(registry.build_catalog_json())

executor = ToolExecutor(registry=registry)
result = executor.execute("calculate", {"expression": "7 * 6"})
print(result["output"]["result"])
```

Expected result: `42`.

Without a repository, `ToolExecutor` uses `NullToolLogRepository`. Add a real repository when audit history is required.

## Shared Satellites

| Satellite (`tool:*` ID) | Function | Side effect |
| --- | --- | --- |
| `calculate` | Evaluates restricted arithmetic syntax | None |
| `unit_convert` | Converts supported length, weight, and temperature units | None |
| `memory_search` | Searches long-term memory with filters and fallback query candidates | Reads configured memory |
| `memory_write` | Writes a validated memory record | Persists to configured memory |
| `gmail_fetch` | Fetches and optionally classifies messages | Reads Gmail/fake source and writes repository |
| `email_classifier` | Classifies stored messages | Writes classifications |
| `email_search` | Searches stored email metadata and content | Reads repository |
| `email_summary` | Summarizes selected/recent emails | Reads repository |
| `draft_reply` | Creates a reply draft | Writes draft repository state |
| `email_send` | Sends a saved or explicit reply | External send when backed by Gmail |
| `notification` | Executes an approved notification | External send when backed by a live notifier |

MailMind also supplies `MailMindSummaryTool`, which groups email information by actionability and impact.

## Collection Agent Satellites

Collection Agent has domain-specific tools for:

- DOB and mobile verification
- entity extraction and memory-backed verification
- loan-policy lookup and offer eligibility
- payment-link creation
- promise capture and follow-up scheduling
- outbound callback scheduling and cancellation
- installment-discount evaluation and application
- premium-hold creation
- SMS and email confirmation
- human escalation
- plan proposal

The Collection Memory Helper adds `update_key_event_memory`.

These Satellites use local data/runtime repositories in tests, but several
represent real-world side effects. Production adapters need approval,
idempotency, timeout, retry, and authorization enforcement outside the model.

## Verification

The shared tool/source group passed 13 tests covering math, Gmail normalization with fakes, classification, summary, drafting, approval-backed notification, email sending with a fake sender, and memory search. A separate smoke verified:

- registry lookup and listing
- JSON and YAML catalog generation
- executor input/output validation
- executor result normalization

Collection tool behavior is covered inside the 139-test Collection Agent group: 117 passed and 22 failed. See [Concrete Agents](./agents.md) for the failing areas.

## Constraints

- Tool execution is synchronous.
- Registering the same name replaces the prior tool without warning.
- Centralized permissions and approval policy are not implemented.
- Timeouts and retries appear in Graph Builder configuration metadata but are not universally enforced by `ToolExecutor`.
- Tool descriptions and schemas may be sent to a model; do not put credentials or private data in them.
