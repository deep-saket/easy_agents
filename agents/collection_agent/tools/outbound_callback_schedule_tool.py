"""Tool for scheduling durable outbound callback jobs."""

from __future__ import annotations

from dataclasses import dataclass

from agents.collection_agent.services.outbound_callback_queue import OutboundCallbackQueue
from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_agent.tools.schemas import (
    OutboundCallbackScheduleInput,
    OutboundCallbackScheduleOutput,
)
from src.tools.base import BaseTool


@dataclass(slots=True)
class OutboundCallbackScheduleTool(
    BaseTool[OutboundCallbackScheduleInput, OutboundCallbackScheduleOutput]
):
    store: CollectionDataStore
    queue: OutboundCallbackQueue
    name: str = "outbound_callback_schedule"
    description: str = "Schedule a durable outbound voice callback for an absolute future time."
    input_schema = OutboundCallbackScheduleInput
    output_schema = OutboundCallbackScheduleOutput

    def execute(self, input: OutboundCallbackScheduleInput) -> OutboundCallbackScheduleOutput:
        customer = self.store.get_customer(input.customer_id) or {}
        phone = str(input.phone or customer.get("phone", "")).strip()
        if not phone:
            raise ValueError(f"No outbound phone number is available for customer {input.customer_id}.")
        job = self.queue.schedule(
            case_id=input.case_id,
            customer_id=input.customer_id,
            session_id=input.session_id,
            callback_time=input.callback_time,
            timezone_name=input.timezone,
            phone=phone,
            max_retries=input.max_retries,
        )
        return OutboundCallbackScheduleOutput(
            job_id=str(job["job_id"]),
            case_id=str(job["case_id"]),
            customer_id=str(job["customer_id"]),
            session_id=str(job["session_id"]),
            scheduled_for=str(job["scheduled_for"]),
            timezone=str(job["timezone"]),
            phone=str(job["phone"]),
            status=str(job["status"]),
            retry_count=int(job.get("retry_count", 0)),
        )
