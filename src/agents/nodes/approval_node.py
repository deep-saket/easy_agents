"""Created: 2026-03-31

Purpose: Implements the reusable approval-gating node for shared agent graphs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from src.agents.nodes.types import ReActState


class ApprovalQueueProtocol(Protocol):
    """Describes the minimal approval queue interface used by the node."""

    def enqueue(self, item: Any) -> Any:
        """Enqueues a pending approval item."""
        ...


@dataclass(slots=True)
class ApprovalNode:
    """Places outbound side effects behind an approval queue when required.

    The node is generic and intentionally light on policy. Agent-specific
    planners or tools decide *whether* a decision requires approval. This node
    only performs the queue handoff when such a payload exists.
    """

    approval_queue: ApprovalQueueProtocol | None = None

    def execute(self, state: ReActState) -> ReActState:
        """Queues a pending approval item when one is present in the state.

        Args:
            state: The current shared graph state.

        Returns:
            A partial state update describing the queued approval when
            applicable, otherwise an empty update.
        """
        if self.approval_queue is None:
            return {}
        approval_item = state.get("approval_item")
        if approval_item is None:
            return {}
        queued_item = self.approval_queue.enqueue(approval_item)
        return {"approval_result": queued_item}
