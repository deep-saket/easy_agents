# Conversation Management Architecture

## Goal

Separate conversational pacing from collections business logic.

`CollectionAgent` remains the decision engine.
`ConversationManagerAgent` inside `agents/collection_agent/conversation_manager` becomes the customer-facing delivery layer.

## Sequence

```mermaid
sequenceDiagram
    participant Customer
    participant CM as ConversationManagerAgent
    participant CA as CollectionAgent
    participant DP as DiscountPlanningAgent

    Customer->>CM: customer message
    CM->>CA: forward turn
    alt response is delayed
        CM-->>Customer: filler / wait message
        CM->>CA: still waiting
    end
    CA->>DP: specialist handoff (when needed)
    DP->>CA: recommendation
    CA->>CM: final response
    CM-->>Customer: deliver final response
```

## Ownership

- `ConversationManagerAgent`
  - latency thresholds
  - filler cadence
  - wait messaging
  - latest-input-wins interruption handling
  - stale-response suppression
  - repeat-request replay
  - VAD-driven barge-in handling and delivery tracking for voice mode
  - response delivery timing
- `CollectionAgent`
  - verification
  - planning
  - routing
  - collections policy
- `DiscountPlanningAgent`
  - hardship / settlement recommendation
  - concession planning
