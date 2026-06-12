"""Tool for cancelling queued outbound callback jobs."""

from __future__ import annotations

from dataclasses import dataclass

from agents.collection_agent.services.outbound_callback_queue import OutboundCallbackQueue
from agents.collection_agent.tools.schemas import (
    OutboundCallbackCancelInput,
    OutboundCallbackCancelOutput,
)
from src.tools.base import BaseTool


@dataclass(slots=True)
class OutboundCallbackCancelTool(
    BaseTool[OutboundCallbackCancelInput, OutboundCallbackCancelOutput]
):
    queue: OutboundCallbackQueue
    name: str = "outbound_callback_cancel"
    description: str = "Cancel scheduled outbound callbacks by job ID or case ID."
    input_schema = OutboundCallbackCancelInput
    output_schema = OutboundCallbackCancelOutput

    def execute(self, input: OutboundCallbackCancelInput) -> OutboundCallbackCancelOutput:
        if not input.job_id and not input.case_id:
            raise ValueError("Provide job_id or case_id to cancel a callback.")
        cancelled = self.queue.cancel(
            job_id=input.job_id,
            case_id=input.case_id,
            reason=input.reason,
        )
        return OutboundCallbackCancelOutput(
            cancelled_job_ids=cancelled,
            status="cancelled" if cancelled else "not_found",
        )
