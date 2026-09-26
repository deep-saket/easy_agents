# Natural-Language Chat Completion Plan

Status: implemented and verified on 2026-09-26

## Goal

Make Wormhole Chat capable of selecting and performing the Galaxy's bounded
local functionality from natural language without keyword, regex, or other
deterministic intent selection.

The non-negotiable boundary is:

```text
model decides intent, Circle, Planet, and actions
code validates schemas and authority
local services execute only the accepted typed plan
```

## Failure audit

| Gap found | Consequence | Resolution |
| --- | --- | --- |
| Regex/keyword Satellite planner | Paraphrases were brittle and decisions were deterministic | Removed `LocalSatellitePlanner`; Gemma now emits the typed plan |
| Lexical Circle/Planet route remained in the Chat path | Model reasoning could be overridden by token overlap | Plan now includes `circle_id` and `planet_id`; membership is validated |
| One planned operation per message | “Remember this and schedule a review” could not work | Plan supports one to five ordered actions |
| Commons existed only behind UI/API | Artifact, knowledge, review, calendar, and approval requests could not run through Chat | Added typed action adapters to the shared `CommonsRuntime` |
| Tool-shaped requests bypassed Gemma | Tools still worked while the model was offline | Every Chat request now requires Gemma planning |
| Canned fallback after rejected generation | System appeared to answer without language generation | Removed fallback output; return verified local results or fail visibly |
| Contiguous-substring Vault retrieval | “Sunday call” missed “Sunday evening call” | Rank bounded query-term overlap inside one selected Vault |
| Planner decisions were not visible | Users could not tell whether the model selected an action | Added planning evidence to API, UI, and traces |

## Implementation phases

- [x] Define strict `NaturalLanguagePlan`, `NaturalLanguageAction`, planning
  evidence, and per-action argument schemas.
- [x] Prompt local Gemma with the live Planet roster, Circle memberships,
  allowed actions, safety rules, and few-shot examples.
- [x] Retry invalid model output through the model at most once; never replace
  it with rule-based intent inference.
- [x] Validate Circle membership, Planet lifecycle, Charter Satellites,
  capabilities, Playbooks, Gates, and selected memory Vault.
- [x] Execute all supported Satellite and Commons actions through reusable
  runtime components.
- [x] Pass the model-selected Planet explicitly into Fleet synthesis.
- [x] Publish model plan, action results, generation evidence, and correlated
  trace events.
- [x] Expose the behavior list and no-fallback guarantee in readiness, Control
  Room Chat, and documentation.
- [x] Test every action type, multi-action execution, unauthorized plans,
  model outage, rejected generation, persistence, and observability.
- [x] Probe representative plans against the real loopback Gemma service.

## Supported action contract

`respond`, `calculate`, `unit_convert`, `memory_write`, `memory_search`,
`artifact_create`, `artifact_list`, `knowledge_add`, `knowledge_search`,
`knowledge_summarize`, `knowledge_verify`, `review_create`, `review_list`,
`calendar_propose`, `calendar_list`, `approval_list`, `approval_decide`, and
`commons_status`.

No action exists for calls, external messages, email send, purchasing,
payments, notifications, or provider calendar mutation. Those require a future
authenticated provider adapter and explicit post-approval execution boundary.

## Verification matrix

The scripted model test exercises all 18 actions through the public Chat API.
Additional cases verify:

- model-selected Circle and Planet appear in the canonical Trajectory;
- one request can write memory and create a Scheduled Review;
- invalid Charter authority triggers exactly two model calls and HTTP 502;
- Gemma outage produces HTTP 503 even for calculation or unit conversion;
- rejected answer generation never produces a deterministic response;
- exact action results remain usable when final synthesis is rejected;
- all planning and execution events share the Mission identifier;
- the browser shows plan evidence and every executed action.

Representative live Gemma probes passed for calculation, memory write,
knowledge search, artifact creation, and energy-startup opportunity advisory
routing.

## Remaining hardening

These are explicit future boundaries, not hidden implementation gaps:

1. Add authenticated, per-principal Galaxy and Vault authorization before
   binding beyond loopback.
2. Add semantic/vector retrieval as an optional local Satellite; current
   memory and evidence retrieval is bounded lexical overlap.
3. Add transaction/compensation policy for multi-action plans that span more
   than one local service. Actions currently validate together and execute in
   order, but completed earlier actions are not rolled back if a later runtime
   operation fails.
4. Add multi-Planet Crew planning. One Chat plan currently has one accountable
   Planet that must authorize every action.
5. Add a provider worker only after approval replay protection, idempotency,
   audit, and explicit user identity are implemented.

See [Chat with Your Galaxy](../guides/chat-with-your-galaxy.md) for usage and
[Commons Circle Runtime](../reference/functionalities/commons.md) for the local
service contracts.
