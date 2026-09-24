# ADR 0001: Canonical Galaxy Vocabulary

- Status: accepted
- Date: 2026-09-24
- Decision owners: repository maintainers

## Context

The repository historically used implementation terms such as guild,
specialist, fleet, gateway, tool, and constellation for several different
ownership, routing, and graph concepts. The overlap made APIs and the Control
Room difficult to explain and made unsafe relationships—for example treating an
external model as an owned component—easy to express accidentally.

## Decision

The vocabulary in [Galaxy Terminology](../galaxy-terminology.md) is canonical
for all new public contracts and user-facing text. Its primary code contracts
live under `easy_agents.galaxy`.

Legacy identifiers and event names remain supported only through explicit,
versioned compatibility boundaries. A display-language cleanup never rewrites
persisted identifiers. Any future terminology change requires:

1. an ADR updating this decision or superseding it;
2. a schema and stable-ID impact review;
3. compatibility and rollback behavior;
4. updates to code, API/CLI, Control Room, documentation, and tests in the same
   implementation slice.

## Consequences

- A Galaxy owns Circles directly.
- A Planet is either Rocky or Giant.
- A Satellite is a specialized Component backed by a technical tool.
- A Constellation is a connected overlay, not a routing layer.
- A Rogue Star is external and accessed through a policy-controlled Orbit.
- Version-1 `guild`, `specialist`, `tool`, and fleet contracts remain readable
  until their documented deprecation window closes.

The terminology matrix is also available programmatically as
`easy_agents.galaxy.TERMINOLOGY`.
