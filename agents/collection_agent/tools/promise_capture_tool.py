from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.tools.base import BaseTool

from agents.collection_agent.tools.common import utc_now
from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_agent.tools.schemas import PromiseCaptureInput, PromiseCaptureOutput


@dataclass(slots=True)
class PromiseCaptureTool(BaseTool[PromiseCaptureInput, PromiseCaptureOutput]):
    store: CollectionDataStore
    name: str = "promise_capture"
    description: str = "Capture a promise-to-pay commitment in local runtime storage."
    input_schema = PromiseCaptureInput
    output_schema = PromiseCaptureOutput

    def execute(self, input: PromiseCaptureInput) -> PromiseCaptureOutput:
        promise_id = f"PTP-{uuid4().hex[:10].upper()}"
        payload = {
            "promise_id": promise_id,
            "case_id": input.case_id,
            "promised_date": input.promised_date,
            "promised_amount": float(input.promised_amount),
            "channel": input.channel,
            "status": "captured",
            "created_at": utc_now().isoformat(),
        }
        self.store.append_runtime("promises.json", payload)
        return PromiseCaptureOutput(
            promise_id=promise_id,
            case_id=input.case_id,
            promised_date=input.promised_date,
            promised_amount=float(input.promised_amount),
            status="captured",
        )
