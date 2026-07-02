"""Collection-specific non-verification React node."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from agents.collection_agent.utils.callback_time_extractor import extract_callback_time
from agents.collection_agent.tools.common import utc_now
from src.nodes.react_node import ReactNode
from src.nodes.types import AgentState
from src.tools.registry import ToolRegistry


@dataclass(slots=True)
class CollectionReactNode(ReactNode):
    """Collection-oriented React behavior for non-verification tooling.

    State Keys Read:
    - `user_input`
    - `steps`
    - `conversation_history`
    - `observations` (session-level ordered tool/node observations)
    - `observation` (compatibility mirror of latest observation)
    - `extracted_entities`
    - `extracted_entities_turn`
    - `verification_entities`
    - `memory` (reads `memory.state` for tool history and entity context)

    State Keys Write:
    - standard React outputs from base node:
      `decision`, `steps`, `prompt`, `system_prompt`, `llm_response`,
      `llm_error`, `llm_status`, `tool_calls`, `pending_tool_calls`
    """

    tool_registry: ToolRegistry | None = None

    def _apply_pre_llm_override(self, *, state: AgentState, context: dict[str, Any]) -> dict[str, Any] | None:
        queued = ReactNode._apply_pre_llm_override(self, state=state, context=context)
        if queued is not None:
            return queued

        memory = state.get("memory")
        memory_state = dict(getattr(memory, "state", {})) if memory is not None else {}
        observations = context.get("observations") if isinstance(context.get("observations"), list) else []
        latest = observations[-1] if observations and isinstance(observations[-1], dict) else {}
        if isinstance(latest.get("tool_phase"), dict):
            latest = latest["tool_phase"]
        latest_tool = str(latest.get("tool_name", "")).strip().lower()
        latest_output = latest.get("output") if isinstance(latest.get("output"), dict) else {}
        tool_completed_this_turn = int(state.get("steps", 0) or 0) > 0
        case_id = str(state.get("case_id") or memory_state.get("active_case_id", "")).strip()
        customer_id = str(state.get("user_id") or memory_state.get("active_user_id", "")).strip()

        if latest_tool == "promise_capture" and tool_completed_this_turn:
            promised_date = str(latest_output.get("promised_date", "")).strip()
            promise_id = str(latest_output.get("promise_id", "")).strip()
            details = (
                dict(memory_state.get("promise_to_pay_details", {}))
                if isinstance(memory_state.get("promise_to_pay_details"), dict)
                else {}
            )
            details.update(latest_output)
            if memory is not None:
                memory.set_state(
                    promise_stage="captured",
                    promise_reference=promise_id,
                    promised_date=promised_date or str(memory_state.get("promised_date", "")).strip(),
                    promise_to_pay_details=details,
                    promise_date_rejection_reason="",
                )
            if case_id and promised_date:
                scheduled_for = self._reminder_date_for_promise(promised_date)
                return {
                    "skip_llm": True,
                    "reason": "Promise-to-pay captured; schedule reminder follow-up.",
                    "decision": self._tool_decision(
                        "followup_schedule",
                        {
                            "case_id": case_id,
                            "scheduled_for": scheduled_for,
                            "preferred_channel": "sms",
                            "reason": "promise_to_pay",
                        },
                    ),
                }

        if latest_tool == "followup_schedule" and tool_completed_this_turn:
            reason = str(latest_output.get("reason", "")).strip().lower()
            if reason == "installment_discount_review":
                details = (
                    dict(memory_state.get("installment_discount_details", {}))
                    if isinstance(memory_state.get("installment_discount_details"), dict)
                    else {}
                )
                details["review_followup_schedule"] = dict(latest_output)
                if memory is not None:
                    memory.set_state(
                        discount_stage="confirmed",
                        installment_discount_details=details,
                        negotiation_stage="confirming_commitment",
                        followup_status="discount_review_scheduled",
                    )
                return {
                    "skip_llm": True,
                    "reason": "Installment discount review follow-up scheduled.",
                    "decision": SimpleNamespace(
                        thought="Discount application, notifications, and review scheduling are complete.",
                        tool_call=None,
                        tool_calls=[],
                        respond_directly=True,
                        response_text=None,
                        done=True,
                        no_tools_required=True,
                    ),
                }

            details = (
                dict(memory_state.get("promise_to_pay_details", {}))
                if isinstance(memory_state.get("promise_to_pay_details"), dict)
                else {}
            )
            details["followup_schedule"] = dict(latest_output)
            promise_id = str(details.get("promise_id", memory_state.get("promise_reference", "")) or "").strip()
            if memory is not None:
                memory.set_state(
                    promise_stage="followup_scheduled",
                    promise_to_pay_details=details,
                    final_disposition="PROMISE_TO_PAY_SCHEDULED",
                    promise_date_rejection_reason="",
                )
            self._append_disposition(
                case_id=case_id,
                disposition_code="PROMISE_TO_PAY_SCHEDULED",
                notes=(
                    f"Promise-to-pay captured and reminder scheduled. Reference: {promise_id}"
                    if promise_id
                    else "Promise-to-pay captured and reminder scheduled."
                ),
            )
            return {
                "skip_llm": True,
                "reason": "Promise-to-pay follow-up scheduled.",
                "decision": SimpleNamespace(
                    thought="Promise-to-pay workflow is ready for customer confirmation.",
                    tool_call=None,
                    tool_calls=[],
                    respond_directly=True,
                    response_text=None,
                    done=True,
                    no_tools_required=True,
                ),
            }

        if (
            str(memory_state.get("payment_commitment_type", "")).strip().upper() == "PROMISE_TO_PAY"
            and str(memory_state.get("promise_stage", "")).strip().lower() == "date_captured"
            and not str(memory_state.get("promise_reference", "")).strip()
            and case_id
        ):
            promised_date = str(memory_state.get("promised_date", "")).strip()
            policy_check = self._validate_promise_date(memory_state=memory_state, promised_date=promised_date)
            if not policy_check["valid"]:
                if memory is not None:
                    memory.set_state(
                        promise_stage="date_invalid",
                        promise_date_rejection_reason=policy_check["reason"],
                    )
                max_days_text = self._promise_window_text(memory_state)
                return {
                    "skip_llm": True,
                    "reason": "Promised date is outside policy window.",
                    "decision": SimpleNamespace(
                        thought="Ask the customer for a valid promise-to-pay date.",
                        tool_call=None,
                        tool_calls=[],
                        respond_directly=True,
                        response_text=(
                            f"That date is outside the allowed payment-commitment window{max_days_text}. "
                            "What earlier date would work for you to clear the full amount?"
                        ),
                        done=True,
                        no_tools_required=True,
                    ),
                }
            amount = float(memory_state.get("active_overdue_amount", 0) or 0)
            if amount > 0:
                if memory is not None:
                    memory.set_state(promise_stage="recording", promise_date_rejection_reason="")
                return {
                    "skip_llm": True,
                    "reason": "Capture full overdue amount promise-to-pay.",
                    "decision": self._tool_decision(
                        "promise_capture",
                        {
                            "case_id": case_id,
                            "promised_date": promised_date,
                            "promised_amount": amount,
                            "channel": "voice",
                        },
                    ),
                }

        if (
            str(memory_state.get("payment_resolution_stage", "")).strip().lower() in {"confirmed", "autopay_offered"}
            and str(memory_state.get("payment_commitment_type", "")).strip().upper() == "FULL_PAYMENT"
            and str(memory_state.get("autopay_response", "")).strip().lower() == "accepted"
            and str(memory_state.get("autopay_stage", "")).strip().lower() != "enabled"
        ):
            details = (
                dict(memory_state.get("full_payment_details", {}))
                if isinstance(memory_state.get("full_payment_details"), dict)
                else {}
            )
            reference = str(details.get("payment_reference_id", "")).strip()
            details["autopay_stage"] = "enabled"
            if memory is not None:
                memory.set_state(
                    autopay_setup_requested=True,
                    autopay_stage="enabled",
                    full_payment_details=details,
                    final_disposition="AUTOPAY_ENABLED",
                )
            self._append_disposition(
                case_id=case_id,
                disposition_code="AUTOPAY_ENABLED",
                notes=(
                    f"Auto-pay enrollment accepted on full-payment link. Reference: {reference}"
                    if reference
                    else "Auto-pay enrollment accepted on full-payment link."
                ),
            )
            return {
                "skip_llm": True,
                "reason": "Auto-pay enrollment accepted.",
                "decision": SimpleNamespace(
                    thought="Auto-pay enrollment has been recorded.",
                    tool_call=None,
                    tool_calls=[],
                    respond_directly=True,
                    response_text=None,
                    done=True,
                    no_tools_required=True,
                ),
            }

        if latest_tool == "payment_link_create" and tool_completed_this_turn:
            if str(memory_state.get("payment_resolution_stage", "")).strip().lower() == "link_requested":
                autopay_requested = bool(memory_state.get("autopay_setup_requested", False)) or str(
                    memory_state.get("autopay_response", "")
                ).strip().lower() == "accepted"
                details = (
                    dict(memory_state.get("full_payment_details", {}))
                    if isinstance(memory_state.get("full_payment_details"), dict)
                    else {}
                )
                details.update(latest_output)
                if autopay_requested:
                    details["autopay_setup_requested"] = True
                    details["autopay_stage"] = "link_created"
                if memory is not None:
                    memory.set_state(
                        payment_resolution_stage="link_created",
                        full_payment_details=details,
                        autopay_setup_requested=autopay_requested,
                        autopay_stage=("link_created" if autopay_requested else memory_state.get("autopay_stage")),
                    )
                reference = str(latest_output.get("payment_reference_id", "")).strip()
                base_message = (
                    f"Your secure payment link for "
                    f"{float(latest_output.get('amount', details.get('amount', 0)) or 0):.2f} is "
                    f"{latest_output.get('payment_url', '')}. Reference: {reference}."
                )
                message = (
                    f"{base_message} You can also confirm auto-pay/standing instruction on the same link."
                    if autopay_requested
                    else base_message
                )
                return {
                    "skip_llm": True,
                    "reason": "Full-payment link created; send it by SMS.",
                    "decision": self._tool_decision(
                        "sms_confirmation_send",
                        {
                            "customer_id": customer_id,
                            "reference_number": reference,
                            "message": message,
                        },
                    ),
                }
            if str(memory_state.get("partial_payment_stage", "")).strip().lower() == "link_requested":
                details = (
                    dict(memory_state.get("partial_payment_details", {}))
                    if isinstance(memory_state.get("partial_payment_details"), dict)
                    else {}
                )
                details.update(latest_output)
                if memory is not None:
                    memory.set_state(
                        partial_payment_stage="link_created",
                        partial_payment_details=details,
                    )
                reference = str(latest_output.get("payment_reference_id", "")).strip()
                message = (
                    f"Your secure partial-payment link for "
                    f"{float(details.get('partial_payment_amount', 0) or 0):.2f} is "
                    f"{latest_output.get('payment_url', '')}. Reference: {reference}."
                )
                return {
                    "skip_llm": True,
                    "reason": "Partial-payment link created; send it by SMS.",
                    "decision": self._tool_decision(
                        "sms_confirmation_send",
                        {
                            "customer_id": customer_id,
                            "reference_number": reference,
                            "message": message,
                        },
                    ),
                }

        if latest_tool == "installment_discount_evaluate" and tool_completed_this_turn:
            if not bool(latest_output.get("eligible", False)):
                return None
            if memory is not None:
                memory.set_state(
                    discount_stage="offered",
                    discount_offered=True,
                    installment_discount_details=dict(latest_output),
                    post_hold_capacity="uncertain",
                    hardship_hold_stage="superseded",
                )
            return {
                "skip_llm": True,
                "reason": "Approved installment discount is ready to present.",
                "decision": SimpleNamespace(
                    thought="Present the approved installment discount.",
                    tool_call=None,
                    tool_calls=[],
                    respond_directly=True,
                    response_text=None,
                    done=True,
                    no_tools_required=True,
                ),
            }

        if latest_tool == "installment_discount_apply" and tool_completed_this_turn:
            details = {
                **(
                    dict(memory_state.get("installment_discount_details", {}))
                    if isinstance(memory_state.get("installment_discount_details"), dict)
                    else {}
                ),
                **latest_output,
            }
            if memory is not None:
                memory.set_state(
                    discount_stage="applied",
                    discount_accepted=True,
                    installment_discount_details=details,
                )
            reference_number = str(latest_output.get("reference_number", "")).strip()
            message = (
                f"Your installment discount has been applied. Reference: {reference_number}. "
                f"Revised amount: {float(latest_output.get('revised_amount', 0) or 0):.2f}."
            )
            return {
                "skip_llm": True,
                "reason": "Installment discount applied; send SMS confirmation.",
                "decision": self._tool_decision(
                    "sms_confirmation_send",
                    {
                        "customer_id": customer_id,
                        "reference_number": reference_number,
                        "message": message,
                    },
                ),
            }

        if latest_tool == "premium_hold_create" and tool_completed_this_turn:
            reference_number = str(latest_output.get("reference_number", "")).strip()
            if not reference_number:
                return None
            hold_details = {
                **(
                    dict(memory_state.get("hardship_hold_details", {}))
                    if isinstance(memory_state.get("hardship_hold_details"), dict)
                    else {}
                ),
                **latest_output,
            }
            if memory is not None:
                memory.set_state(
                    hardship_hold_stage="created",
                    hardship_hold_details=hold_details,
                )
            message = (
                f"Your premium hold has been arranged. Reference: {reference_number}. "
                f"The hold is active until {latest_output.get('effective_until', '')}."
            )
            return {
                "skip_llm": True,
                "reason": "Premium hold created; send SMS confirmation.",
                "decision": self._tool_decision(
                    "sms_confirmation_send",
                    {
                        "customer_id": customer_id,
                        "reference_number": reference_number,
                        "message": message,
                    },
                ),
            }

        if latest_tool == "sms_confirmation_send" and tool_completed_this_turn:
            if str(memory_state.get("payment_resolution_stage", "")).strip().lower() == "link_created":
                autopay_requested = bool(memory_state.get("autopay_setup_requested", False)) or str(
                    memory_state.get("autopay_response", "")
                ).strip().lower() == "accepted"
                details = (
                    dict(memory_state.get("full_payment_details", {}))
                    if isinstance(memory_state.get("full_payment_details"), dict)
                    else {}
                )
                details["sms_confirmation"] = dict(latest_output)
                if autopay_requested:
                    details["autopay_stage"] = "enabled"
                reference = str(details.get("payment_reference_id", latest_output.get("reference_number", ""))).strip()
                if memory is not None:
                    memory.set_state(
                        payment_resolution_stage="confirmed",
                        full_payment_details=details,
                        followup_status="awaiting_full_payment",
                        final_disposition=("AUTOPAY_ENABLED" if autopay_requested else "PAID_IN_FULL"),
                        autopay_setup_requested=autopay_requested,
                        autopay_stage=("enabled" if autopay_requested else memory_state.get("autopay_stage")),
                    )
                self._append_disposition(
                    case_id=case_id,
                    disposition_code="PAID_IN_FULL",
                    notes=f"Full-payment link delivered. Reference: {reference}",
                )
                if autopay_requested:
                    self._append_disposition(
                        case_id=case_id,
                        disposition_code="AUTOPAY_ENABLED",
                        notes=f"Auto-pay enrollment link delivered. Reference: {reference}",
                    )
                return {
                    "skip_llm": True,
                    "reason": "Full-payment link sent by SMS.",
                    "decision": SimpleNamespace(
                        thought="Full-payment link delivery is complete.",
                        tool_call=None,
                        tool_calls=[],
                        respond_directly=True,
                        response_text=None,
                        done=True,
                        no_tools_required=True,
                    ),
                }
            if str(memory_state.get("partial_payment_stage", "")).strip().lower() == "link_created":
                details = (
                    dict(memory_state.get("partial_payment_details", {}))
                    if isinstance(memory_state.get("partial_payment_details"), dict)
                    else {}
                )
                details["sms_confirmation"] = dict(latest_output)
                if memory is not None:
                    memory.set_state(
                        partial_payment_stage="confirmed",
                        partial_payment_details=details,
                        followup_status="awaiting_partial_payment",
                    )
                return {
                    "skip_llm": True,
                    "reason": "Partial-payment link sent by SMS.",
                    "decision": SimpleNamespace(
                        thought="Partial-payment link delivery is complete.",
                        tool_call=None,
                        tool_calls=[],
                        respond_directly=True,
                        response_text=None,
                        done=True,
                        no_tools_required=True,
                    ),
                }
            if str(memory_state.get("discount_stage", "")).strip().lower() == "applied":
                details = (
                    dict(memory_state.get("installment_discount_details", {}))
                    if isinstance(memory_state.get("installment_discount_details"), dict)
                    else {}
                )
                details["sms_confirmation"] = dict(latest_output)
                if memory is not None:
                    memory.set_state(
                        discount_stage="sms_sent",
                        installment_discount_details=details,
                    )
                reference_number = str(latest_output.get("reference_number", "")).strip()
                message = (
                    f"Your installment discount has been applied. Reference: {reference_number}. "
                    f"Revised amount: {float(details.get('revised_amount', 0) or 0):.2f}."
                )
                return {
                    "skip_llm": True,
                    "reason": "Discount SMS sent; send email confirmation.",
                    "decision": self._tool_decision(
                        "email_confirmation_send",
                        {
                            "customer_id": customer_id,
                            "reference_number": reference_number,
                            "subject": "Installment discount confirmation",
                            "message": message,
                        },
                    ),
                }
            reference_number = str(latest_output.get("reference_number", "")).strip()
            hold_details = (
                dict(memory_state.get("hardship_hold_details", {}))
                if isinstance(memory_state.get("hardship_hold_details"), dict)
                else {}
            )
            hold_details["sms_confirmation"] = dict(latest_output)
            if memory is not None:
                memory.set_state(
                    hardship_hold_stage="sms_sent",
                    hardship_hold_details=hold_details,
                )
            message = (
                f"Your premium hold has been arranged. Reference: {reference_number}. "
                f"The hold is active until {hold_details.get('effective_until', '')}."
            )
            return {
                "skip_llm": True,
                "reason": "SMS confirmation sent; send email confirmation.",
                "decision": self._tool_decision(
                    "email_confirmation_send",
                    {
                        "customer_id": customer_id,
                        "reference_number": reference_number,
                        "subject": "Premium hold confirmation",
                        "message": message,
                    },
                ),
            }

        if latest_tool == "email_confirmation_send" and tool_completed_this_turn:
            if str(memory_state.get("discount_stage", "")).strip().lower() == "sms_sent":
                details = (
                    dict(memory_state.get("installment_discount_details", {}))
                    if isinstance(memory_state.get("installment_discount_details"), dict)
                    else {}
                )
                details["email_confirmation"] = dict(latest_output)
            if memory is not None:
                memory.set_state(
                    discount_stage="review_scheduling",
                    installment_discount_details=details,
                    negotiation_stage="confirming_commitment",
                )
            review_after_months = int(details.get("review_after_months", 0) or 0)
            if review_after_months > 0 and case_id:
                scheduled_for = self._add_months(datetime.now(UTC).date(), review_after_months).isoformat()
                return {
                    "skip_llm": True,
                    "reason": "Discount and both confirmations completed; schedule review follow-up.",
                    "decision": self._tool_decision(
                        "followup_schedule",
                        {
                            "case_id": case_id,
                            "scheduled_for": scheduled_for,
                            "preferred_channel": "voice",
                            "reason": "installment_discount_review",
                        },
                    ),
                }
            if memory is not None:
                memory.set_state(discount_stage="confirmed")
            return {
                "skip_llm": True,
                "reason": "Discount and both confirmations completed.",
                "decision": SimpleNamespace(
                        thought="Discount application and notifications are complete.",
                        tool_call=None,
                        tool_calls=[],
                        respond_directly=True,
                        response_text=None,
                        done=True,
                        no_tools_required=True,
                    ),
                }
            hold_details = (
                dict(memory_state.get("hardship_hold_details", {}))
                if isinstance(memory_state.get("hardship_hold_details"), dict)
                else {}
            )
            hold_details["email_confirmation"] = dict(latest_output)
            if memory is not None:
                memory.set_state(
                    hardship_hold_stage="confirmed",
                    hardship_hold_details=hold_details,
                    negotiation_stage="confirming_commitment",
                )
            return {
                "skip_llm": True,
                "reason": "Premium hold and both confirmations completed.",
                "decision": SimpleNamespace(
                    thought="Hold creation and notifications are complete; continue to customer confirmation.",
                    tool_call=None,
                    tool_calls=[],
                    respond_directly=True,
                    response_text=None,
                    done=True,
                    no_tools_required=True,
                ),
            }

        if latest_tool == "outbound_callback_schedule" and tool_completed_this_turn:
            scheduled_callback_time = ""
            latest_input = latest.get("input") if isinstance(latest.get("input"), dict) else {}
            if isinstance(latest_input, dict):
                scheduled_callback_time = str(latest_input.get("callback_time", "")).strip()
            if memory is not None:
                memory.set_state(
                    outbound_callback_job_id=latest_output.get("job_id"),
                    outbound_callback_scheduled_for=latest_output.get("scheduled_for"),
                    outbound_callback_status=latest_output.get("status"),
                    wrong_party_callback_stage=(
                        "completed"
                        if str(latest_output.get("status", "")).strip().lower() == "scheduled"
                        else str(memory_state.get("wrong_party_callback_stage", "")).strip().lower() or None
                    ),
                    wrong_party_callback_time=(
                        scheduled_callback_time
                        or memory_state.get("wrong_party_callback_time")
                    ),
                )
            return {
                "skip_llm": True,
                "reason": "Outbound callback scheduling tool completed.",
                "decision": SimpleNamespace(
                    thought="Callback scheduling is complete; continue to customer confirmation.",
                    tool_call=None,
                    tool_calls=[],
                    respond_directly=True,
                    response_text=None,
                    done=True,
                    no_tools_required=True,
                ),
            }
        if latest_tool == "outbound_callback_cancel" and tool_completed_this_turn:
            if memory is not None:
                memory.set_state(outbound_callback_status=latest_output.get("status"))
            return {
                "skip_llm": True,
                "reason": "Outbound callback cancellation tool completed.",
                "decision": SimpleNamespace(
                    thought="Callback cancellation is complete.",
                    tool_call=None,
                    tool_calls=[],
                    respond_directly=True,
                    response_text=None,
                    done=True,
                    no_tools_required=True,
                ),
            }
        if latest_tool == "human_escalation" and tool_completed_this_turn:
            if memory is not None:
                memory.set_state(
                    human_escalation_id=latest_output.get("escalation_id"),
                    human_escalation_queue=latest_output.get("queue"),
                    human_escalation_priority=latest_output.get("priority"),
                    human_escalation_status=latest_output.get("status"),
                    human_transfer_status="pending",
                    conversation_handoff="human_specialist",
                )
            return {
                "skip_llm": True,
                "reason": "Human escalation queued; continue to live transfer response.",
                "decision": SimpleNamespace(
                    thought="Human escalation has been queued; transfer customer to specialist.",
                    tool_call=None,
                    tool_calls=[],
                    respond_directly=True,
                    response_text=None,
                    done=True,
                    no_tools_required=True,
                ),
            }

        user_input = str(state.get("user_input", ""))
        lowered = user_input.lower()
        hold_stage = str(memory_state.get("hardship_hold_stage", "")).strip().lower()
        discount_stage = str(memory_state.get("discount_stage", "")).strip().lower()
        partial_stage = str(memory_state.get("partial_payment_stage", "")).strip().lower()
        if (
            (
                str(memory_state.get("negotiation_stage", "")).strip().lower() == "hardship_options_exhausted"
                or bool(
                    (
                        memory_state.get("hardship_context", {})
                        if isinstance(memory_state.get("hardship_context"), dict)
                        else {}
                    ).get("hardship_detected", False)
                )
            )
            and (
                discount_stage in {"counter_offer", "rejected"}
                or str(memory_state.get("discount_response", "")).strip().lower() in {"counter", "rejected"}
            )
            and bool(memory_state.get("discount_offered", False))
            and bool(memory_state.get("generic_options_offered_after_discount", False))
            and str(memory_state.get("human_escalation_status", "")).strip().lower() != "queued"
            and case_id
        ):
            if memory is not None:
                memory.set_state(negotiation_stage="hardship_options_exhausted")
            return {
                "skip_llm": True,
                "reason": "Exhausted hardship options require human specialist escalation.",
                "decision": self._tool_decision(
                    "human_escalation",
                    {
                        "case_id": case_id,
                        "reason": "hardship_options_exhausted",
                        "evidence_summary": (
                            "Customer rejected the premium hold and installment discount; "
                            "no additional approved hardship option is available in the current policy."
                        ),
                    },
                ),
            }
        if partial_stage == "link_offered" and self._is_affirmative(user_input):
            details = (
                memory_state.get("partial_payment_details")
                if isinstance(memory_state.get("partial_payment_details"), dict)
                else {}
            )
            amount = float(details.get("partial_payment_amount", 0) or 0)
            if case_id and amount > 0:
                if memory is not None:
                    memory.set_state(partial_payment_stage="link_requested")
                return {
                    "skip_llm": True,
                    "reason": "Customer accepted the partial-payment link.",
                    "decision": self._tool_decision(
                        "payment_link_create",
                        {
                            "case_id": case_id,
                            "amount": amount,
                            "channel": "sms",
                        },
                    ),
                }
        if (
            str(memory_state.get("payment_resolution_stage", "")).strip().lower() in {"options_offered", "link_offered"}
            and str(memory_state.get("payment_commitment_type", "")).strip().upper() == "FULL_PAYMENT"
            and str(memory_state.get("payment_option_response", "")).strip().lower() == "payment_link"
        ):
            amount = float(memory_state.get("active_overdue_amount", 0) or 0)
            if case_id and amount > 0:
                if memory is not None:
                    memory.set_state(payment_resolution_stage="link_requested")
                return {
                    "skip_llm": True,
                    "reason": "Customer requested the full-payment link.",
                    "decision": self._tool_decision(
                        "payment_link_create",
                        {
                            "case_id": case_id,
                            "amount": amount,
                            "channel": "sms",
                        },
                    ),
                }
        if (
            hold_stage == "offered"
            and str(memory_state.get("hold_response", "")).strip().lower() == "uncertain"
        ):
            program = self._eligible_discount_program(memory_state)
            original_amount = float(memory_state.get("active_overdue_amount", 0) or 0)
            if program and case_id and customer_id and original_amount > 0:
                if memory is not None:
                    memory.set_state(
                        discount_stage="evaluating",
                        post_hold_capacity="uncertain",
                        installment_discount_program=dict(program),
                        hardship_hold_stage="superseded",
                    )
                return {
                    "skip_llm": True,
                    "reason": "Customer is unsure after the hold; evaluate installment discount.",
                    "decision": self._tool_decision(
                        "installment_discount_evaluate",
                        {
                            "case_id": case_id,
                            "customer_id": customer_id,
                            "program_id": str(program.get("program_id", "")),
                            "original_amount": original_amount,
                        },
                    ),
                }
        if (
            discount_stage in {"offered", "accepted"}
            and str(memory_state.get("discount_response", "")).strip().lower() == "accepted"
        ):
            details = (
                memory_state.get("installment_discount_details")
                if isinstance(memory_state.get("installment_discount_details"), dict)
                else {}
            )
            if case_id and customer_id and details:
                return {
                    "skip_llm": True,
                    "reason": "Customer accepted the approved installment discount.",
                    "decision": self._tool_decision(
                        "installment_discount_apply",
                        {
                            "case_id": case_id,
                            "customer_id": customer_id,
                            "program_id": str(details.get("program_id", "")),
                            "original_amount": float(memory_state.get("active_overdue_amount", 0) or 0),
                            "discount_pct": float(details.get("discount_pct", 0) or 0),
                            "revised_amount": float(details.get("revised_amount", 0) or 0),
                        },
                    ),
                }
        if (
            hold_stage == "offered"
            and not self._has_active_discount_branch(memory_state)
            and str(memory_state.get("hold_response", "")).strip().lower() == "accepted"
        ):
            program = (
                memory_state.get("hardship_hold_program")
                if isinstance(memory_state.get("hardship_hold_program"), dict)
                else {}
            )
            program_id = str(program.get("program_id", "")).strip()
            hold_months = int(program.get("max_hold_months", 0) or 0)
            if case_id and customer_id and program_id and hold_months > 0:
                return {
                    "skip_llm": True,
                    "reason": "Customer accepted the eligible premium hold.",
                    "decision": self._tool_decision(
                        "premium_hold_create",
                        {
                            "case_id": case_id,
                            "customer_id": customer_id,
                            "program_id": program_id,
                            "hold_months": hold_months,
                        },
                    ),
                }
        if "callback" in lowered and any(token in lowered for token in ("cancel", "remove", "do not call", "don't call")):
            return {
                "skip_llm": True,
                "reason": "Customer requested callback cancellation.",
                "decision": self._tool_decision(
                    "outbound_callback_cancel",
                    {
                        "job_id": memory_state.get("outbound_callback_job_id"),
                        "case_id": case_id or None,
                        "reason": "customer_requested_cancellation",
                    },
                ),
            }

        right_party_status = str(memory_state.get("right_party_status", "")).strip().lower()
        callback_stage = str(memory_state.get("wrong_party_callback_stage", "")).strip().lower()
        if right_party_status != "wrong_party" or callback_stage not in {
            "privacy_notice_given",
            "awaiting_callback",
        }:
            return None
        callback_time = extract_callback_time(user_input, llm=self.llm)
        if not callback_time or not case_id or not customer_id:
            return None

        for observation in reversed(observations):
            if not isinstance(observation, dict):
                continue
            payload = observation.get("tool_phase") if isinstance(observation.get("tool_phase"), dict) else observation
            if str(payload.get("tool_name", "")).strip().lower() != "outbound_callback_schedule":
                continue
            tool_input = payload.get("input") if isinstance(payload.get("input"), dict) else {}
            if tool_input.get("case_id") == case_id and tool_input.get("callback_time") == callback_time:
                return None

        return {
            "skip_llm": True,
            "reason": "Schedule privacy-safe outbound callback.",
            "decision": self._tool_decision(
                "outbound_callback_schedule",
                {
                    "case_id": case_id,
                    "customer_id": customer_id,
                    "session_id": str(state.get("session_id", "")).strip() or "collection-session",
                    "callback_time": callback_time,
                    "timezone": str(memory_state.get("timezone", "Asia/Kolkata")).strip() or "Asia/Kolkata",
                    "max_retries": 3,
                },
            ),
        }

    @staticmethod
    def _validate_promise_date(*, memory_state: dict[str, Any], promised_date: str) -> dict[str, Any]:
        parsed = CollectionReactNode._parse_promise_date(promised_date)
        if parsed is None:
            return {"valid": True, "reason": "unparsed_relative_date"}
        active_context = (
            memory_state.get("active_collection_context")
            if isinstance(memory_state.get("active_collection_context"), dict)
            else {}
        )
        policy = active_context.get("policy") if isinstance(active_context.get("policy"), dict) else {}
        max_days = int(policy.get("max_promise_days", 0) or 0)
        if max_days <= 0:
            return {"valid": True, "reason": "no_policy_limit"}
        today = datetime.now(UTC).date()
        delta_days = (parsed - today).days
        if delta_days < 0:
            return {"valid": False, "reason": "promised_date_in_past"}
        if delta_days > max_days:
            return {"valid": False, "reason": f"promised_date_exceeds_{max_days}_days"}
        return {"valid": True, "reason": "within_policy"}

    @staticmethod
    def _promise_window_text(memory_state: dict[str, Any]) -> str:
        active_context = (
            memory_state.get("active_collection_context")
            if isinstance(memory_state.get("active_collection_context"), dict)
            else {}
        )
        policy = active_context.get("policy") if isinstance(active_context.get("policy"), dict) else {}
        max_days = int(policy.get("max_promise_days", 0) or 0)
        return f" of {max_days} days for this account" if max_days > 0 else " for this account"

    @staticmethod
    def _reminder_date_for_promise(promised_date: str) -> str:
        parsed = CollectionReactNode._parse_promise_date(promised_date)
        if parsed is None:
            return promised_date
        reminder = parsed - timedelta(days=1)
        if reminder < datetime.now(UTC).date():
            reminder = parsed
        return reminder.isoformat()

    @staticmethod
    def _parse_promise_date(promised_date: str) -> date | None:
        text = str(promised_date or "").strip().lower()
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                pass
        today = datetime.now(UTC).date()
        if text == "tomorrow":
            return today + timedelta(days=1)
        match = re.search(r"\b(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\b", text)
        if match:
            day = int(match.group(1))
            if 1 <= day <= 31:
                year = today.year
                month = today.month
                for _ in range(2):
                    try:
                        candidate = date(year, month, day)
                    except ValueError:
                        month += 1
                        if month > 12:
                            month = 1
                            year += 1
                        continue
                    if candidate >= today:
                        return candidate
                    month += 1
                    if month > 12:
                        month = 1
                        year += 1
        if "end of the month" in text or "end of month" in text:
            next_month = date(today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1, 1)
            return next_month - timedelta(days=1)
        weekday_match = re.search(r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text)
        if weekday_match:
            weekdays = {
                "monday": 0,
                "tuesday": 1,
                "wednesday": 2,
                "thursday": 3,
                "friday": 4,
                "saturday": 5,
                "sunday": 6,
            }
            target = weekdays[weekday_match.group(1)]
            days = (target - today.weekday()) % 7
            return today + timedelta(days=days or 7)
        return None

    @staticmethod
    def _add_months(value: date, months: int) -> date:
        month_index = value.month - 1 + max(int(months), 0)
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        last_day = (
            date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
            - timedelta(days=1)
        ).day
        return date(year, month, min(value.day, last_day))

    @staticmethod
    def _is_affirmative(text: str) -> bool:
        normalized = re.sub(r"[^a-z0-9\s]", " ", str(text).lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return any(
            phrase in normalized
            for phrase in (
                "yes",
                "that would help",
                "would really help",
                "sounds good",
                "i agree",
                "please do",
                "go ahead",
                "okay",
                "ok",
            )
        )

    @staticmethod
    def _eligible_discount_program(memory_state: dict[str, Any]) -> dict[str, Any]:
        hardship = (
            memory_state.get("hardship_context")
            if isinstance(memory_state.get("hardship_context"), dict)
            else {}
        )
        reason = str(hardship.get("hardship_reason", "")).strip().lower()
        context = (
            memory_state.get("active_collection_context")
            if isinstance(memory_state.get("active_collection_context"), dict)
            else {}
        )
        case = context.get("case") if isinstance(context.get("case"), dict) else {}
        loan_id = str(case.get("loan_id", memory_state.get("active_loan_id", ""))).strip().upper()
        programs = (
            memory_state.get("assistance_programs")
            if isinstance(memory_state.get("assistance_programs"), list)
            else []
        )
        for item in programs:
            if not isinstance(item, dict) or str(item.get("program_type", "")).strip() != "installment_discount":
                continue
            loan_ids = {str(value).strip().upper() for value in item.get("eligible_loan_ids", [])}
            reasons = {str(value).strip().lower() for value in item.get("hardship_reasons", [])}
            if loan_ids and loan_id not in loan_ids:
                continue
            if reasons and reason not in reasons:
                continue
            return dict(item)
        return {}

    def _append_disposition(self, *, case_id: str, disposition_code: str, notes: str) -> None:
        if not self.tool_registry or not case_id:
            return
        store = None
        for tool in self.tool_registry.list_tools():
            candidate = getattr(tool, "store", None)
            if candidate is not None:
                store = candidate
                break
        if store is None:
            return
        store.append_runtime(
            "dispositions.json",
            {
                "audit_id": f"AUD-{uuid4().hex[:10].upper()}",
                "case_id": case_id,
                "disposition_code": disposition_code,
                "notes": notes,
                "updated_at": utc_now().isoformat(),
            },
        )

    @staticmethod
    def _has_active_discount_branch(memory_state: dict[str, Any]) -> bool:
        stage = str(memory_state.get("discount_stage", "")).strip().lower()
        details = memory_state.get("installment_discount_details")
        return stage in {
            "evaluating",
            "offered",
            "accepted",
            "applied",
            "sms_sent",
            "confirmed",
        } or (
            isinstance(details, dict)
            and bool(details.get("eligible", False))
            and str(details.get("approval_status", "")).strip().lower() == "approved"
        )

    def _build_context_for_react(self, state: AgentState) -> dict[str, Any]:
        memory = state.get("memory")
        memory_state = dict(getattr(memory, "state", {})) if memory is not None else {}

        observations = list(state.get("observations", [])) if isinstance(state.get("observations"), list) else []
        if not observations and isinstance(state.get("observation"), dict):
            current_observation = state.get("observation")
            if isinstance(current_observation, dict) and isinstance(current_observation.get("tool_phase"), dict):
                current_observation = current_observation.get("tool_phase")
            if isinstance(current_observation, dict) and current_observation:
                observations = [current_observation]
        observations = [item for item in observations if isinstance(item, dict)]

        extracted_entities = state.get("extracted_entities")
        if not isinstance(extracted_entities, dict):
            extracted_entities = (
                dict(memory_state.get("extracted_entities", {}))
                if isinstance(memory_state.get("extracted_entities"), dict)
                else {}
            )

        extracted_entities_turn = state.get("extracted_entities_turn")
        if not isinstance(extracted_entities_turn, dict):
            extracted_entities_turn = (
                dict(memory_state.get("extracted_entities_turn", {}))
                if isinstance(memory_state.get("extracted_entities_turn"), dict)
                else {}
            )

        verification_entities = state.get("verification_entities")
        if not isinstance(verification_entities, dict):
            verification_entities = (
                dict(memory_state.get("verification_entities", {}))
                if isinstance(memory_state.get("verification_entities"), dict)
                else {}
            )
        hardship_context = state.get("hardship_context")
        if not isinstance(hardship_context, dict):
            hardship_context = (
                dict(memory_state.get("hardship_context", {}))
                if isinstance(memory_state.get("hardship_context"), dict)
                else {}
            )

        conversation_history = state.get("conversation_history")
        if not isinstance(conversation_history, list):
            conversation_history = (
                list(memory_state.get("conversation_history", []))
                if isinstance(memory_state.get("conversation_history"), list)
                else []
            )
        recent_conversation: list[dict[str, str]] = []
        for item in conversation_history[-8:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", "")).strip()
            if not role or not content:
                continue
            recent_conversation.append(
                {
                    "role": role,
                    "content": (content[:280] + " ...[truncated]") if len(content) > 280 else content,
                }
            )

        return {
            "available_tools": self.available_tools if self.available_tools is not None else state.get("available_tools"),
            "user_input": state.get("user_input"),
            "observations": observations,
            "observation": observations[-1] if observations else None,
            "recent_conversation": recent_conversation,
            "steps": state.get("steps", 0),
            "extracted_entities": extracted_entities,
            "extracted_entities_turn": extracted_entities_turn,
            "verification_entities": verification_entities,
            "conversation_mode": state.get("conversation_mode") or memory_state.get("conversation_mode"),
            "negotiation_stage": state.get("negotiation_stage") or memory_state.get("negotiation_stage"),
            "customer_payment_posture": state.get("customer_payment_posture")
            or memory_state.get("customer_payment_posture"),
            "hardship_context": hardship_context,
            "response_mode": state.get("response_mode") or memory_state.get("response_mode"),
            "active_dialogue_owner": state.get("active_dialogue_owner") or memory_state.get("active_dialogue_owner"),
        }

    def _apply_post_llm_override(self, *, state: AgentState, context: dict[str, Any], decision: Any) -> Any:
        del state, context
        decision = self._sanitize_tool_decision(decision)
        if not bool(getattr(decision, "no_tools_required", False)):
            return decision
        return SimpleNamespace(
            thought=str(getattr(decision, "thought", "") or "No tool execution is required."),
            tool_call=None,
            tool_calls=[],
            respond_directly=bool(getattr(decision, "respond_directly", False)),
            response_text=getattr(decision, "response_text", None),
            done=True,
            no_tools_required=True,
        )

    def _sanitize_tool_decision(self, decision: Any) -> Any:
        proposed_calls = self._decision_tool_calls(decision) or []
        if not proposed_calls:
            return decision
        valid_calls: list[dict[str, Any]] = []
        for item in proposed_calls:
            normalized = self._validate_tool_call(item)
            if normalized is not None:
                valid_calls.append(normalized)
        if not valid_calls:
            return SimpleNamespace(
                thought=str(getattr(decision, "thought", "") or "No valid tool execution is required."),
                tool_call=None,
                tool_calls=[],
                respond_directly=bool(getattr(decision, "respond_directly", False)),
                response_text=getattr(decision, "response_text", None),
                done=True,
                no_tools_required=True,
            )
        first = valid_calls[0]
        return SimpleNamespace(
            thought=str(getattr(decision, "thought", "") or f"Use {first['tool_name']}."),
            tool_call=SimpleNamespace(
                tool_name=str(first.get("tool_name", "")).strip(),
                arguments=first.get("arguments", {}) if isinstance(first.get("arguments"), dict) else {},
            ),
            tool_calls=valid_calls,
            respond_directly=False,
            response_text=None,
            done=False,
            no_tools_required=False,
        )

    def _validate_tool_call(self, item: dict[str, Any]) -> dict[str, Any] | None:
        if self.tool_registry is None or not isinstance(item, dict):
            return item if isinstance(item, dict) else None
        tool_name = str(item.get("tool_name", "")).strip()
        if not tool_name:
            return None
        arguments = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
        try:
            tool = self.tool_registry.get(tool_name)
            validated_input = tool.input_schema.model_validate(arguments)
        except Exception:
            return None
        return {
            "tool_name": tool_name,
            "arguments": validated_input.model_dump(mode="json"),
        }

    @staticmethod
    def _tool_decision(tool_name: str, arguments: dict[str, Any]) -> Any:
        return SimpleNamespace(
            thought=f"Collection pre-rule chose tool `{tool_name}`.",
            tool_call=SimpleNamespace(tool_name=tool_name, arguments=arguments),
            respond_directly=False,
            response_text=None,
            done=False,
        )
