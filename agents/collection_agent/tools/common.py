"""Shared helpers for Collection Agent tool modules."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from agents.collection_agent.tools.schemas import CaseRecord


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_case_record(row: dict) -> CaseRecord:
    return CaseRecord(
        case_id=str(row.get("case_id")),
        customer_id=str(row.get("customer_id")),
        loan_id=str(row.get("loan_id")),
        portfolio_id=str(row.get("portfolio_id")),
        product=str(row.get("product", "loan")),
        dpd=int(row.get("dpd", 0)),
        emi_amount=float(row.get("emi_amount", 0.0)),
        overdue_amount=float(row.get("overdue_amount", 0.0)),
        late_fee=float(row.get("late_fee", 0.0)),
        status=str(row.get("status", "open")),
        risk_band=str(row.get("risk_band", "medium")),
    )


def observation_to_response(observation: dict) -> str:
    if isinstance(observation.get("tool_phase"), dict):
        observation = observation["tool_phase"]
    tool_name = str(observation.get("tool_name", "unknown"))
    output = observation.get("output")
    if isinstance(output, dict):
        pairs = ", ".join(f"{key}={value}" for key, value in list(output.items())[:6])
        return f"Executed {tool_name}: {pairs}" if pairs else f"Executed {tool_name}."
    return f"Executed {tool_name}."


def followup_decision_from_observation(observation: dict) -> SimpleNamespace | None:
    if isinstance(observation.get("tool_phase"), dict):
        observation = observation["tool_phase"]
    tool_name = str(observation.get("tool_name", ""))
    output = observation.get("output") if isinstance(observation.get("output"), dict) else {}

    if tool_name == "payment_link_create":
        ref_id = output.get("payment_reference_id")
        if ref_id:
            return SimpleNamespace(
                thought="Checking payment status for generated payment link.",
                tool_call=SimpleNamespace(tool_name="payment_status_check", arguments={"payment_reference_id": ref_id}),
                respond_directly=False,
                response_text=None,
                done=False,
            )

    if tool_name == "promise_capture":
        case_id = output.get("case_id")
        promised_date = output.get("promised_date")
        if case_id and promised_date:
            return SimpleNamespace(
                thought="Scheduling follow-up from captured promise-to-pay.",
                tool_call=SimpleNamespace(
                    tool_name="followup_schedule",
                    arguments={
                        "case_id": case_id,
                        "scheduled_for": promised_date,
                        "preferred_channel": "voice",
                        "reason": "promise_to_pay",
                    },
                ),
                respond_directly=False,
                response_text=None,
                done=False,
            )
    return None
