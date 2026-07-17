"""Runtime projection of Collection Agent workflow state into a plan tree."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agents.collection_agent.utils.callback_time_extractor import extract_callback_time
from agents.collection_agent.utils.plan_proposal_utils import (
    effective_mode,
    fresh_debug_state,
    get_existing_conversation_plan,
    is_conversation_termination,
    is_right_party_denial,
    looks_like_callback_time,
    latest_observation,
    overlay_negotiation_state_from_graph,
    overlay_verification_state_from_graph,
)
from src.nodes.base import BaseGraphNode
from src.nodes.types import AgentState, NodeUpdate


_TERMINAL_STATES = {"done", "blocked", "skipped"}
_VALID_STATES = {*_TERMINAL_STATES, "pending"}


@dataclass(slots=True)
class PlanProposalGraphNode(BaseGraphNode):
    """Projects authoritative runtime state into the conversation plan."""

    llm: Any | None = None
    system_prompt: str = ""
    user_prompt: str = ""
    classifier_system_prompt: str = ""
    classifier_user_prompt: str = ""
    strict_llm_mode: bool = True
    max_json_chars: int = 900
    last_debug: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    plan_graph_debug: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    def execute(self, state: AgentState) -> NodeUpdate:
        self._record_llm_usage(state, node_name="plan_proposal_graph")
        self.last_debug = fresh_debug_state()
        memory = state.get("memory")
        raw_memory = dict(getattr(memory, "state", {})) if memory is not None else {}
        memory_state = (
            dict(state.get("plan_prepared_memory_state"))
            if isinstance(state.get("plan_prepared_memory_state"), dict)
            else overlay_negotiation_state_from_graph(
                state=state,
                memory_state=overlay_verification_state_from_graph(
                    state=state,
                    memory_state=raw_memory,
                ),
            )
        )
        user_input = str(state.get("user_input", ""))
        self._overlay_wrong_party_state(memory_state=memory_state, user_input=user_input)

        existing_plan = get_existing_conversation_plan(state=state, memory_state=memory_state)
        plan_mode = str(
            state.get(
                "plan_mode",
                effective_mode(
                    memory_state=memory_state,
                    default=str(raw_memory.get("mode", "strict_collections")),
                ),
            )
        ).strip() or "strict_collections"
        plan_origin = str(state.get("plan_origin", "react")).strip() or "react"
        response_target = str(state.get("response_target", "customer")).strip().lower() or "customer"
        route = str(state.get("route", "continue")).strip().lower() or "continue"
        plan_signals = state.get("plan_signals") if isinstance(state.get("plan_signals"), dict) else {}

        observation = latest_observation(state)
        observed_tool = str(state.get("observed_tool", "")).strip()
        observed_tool_output = (
            dict(state.get("observed_tool_output"))
            if isinstance(state.get("observed_tool_output"), dict)
            else (
                dict(observation.get("output", {}))
                if isinstance(observation, dict) and isinstance(observation.get("output"), dict)
                else {}
            )
        )

        plan = self._project_plan(
            existing_plan=existing_plan,
            memory_state=memory_state,
            user_input=user_input,
            mode=plan_mode,
            plan_origin=plan_origin,
            response_target=response_target,
            route=route,
            plan_signals=plan_signals,
            observed_tool=observed_tool,
            observed_tool_output=observed_tool_output,
        )
        if memory is not None:
            memory.set_state(active_conversation_plan=plan)

        self.plan_graph_debug = {
            "plan_id": plan.get("plan_id"),
            "version": plan.get("version"),
            "current_node_id": plan.get("current_node_id"),
            "next_node_ids": plan.get("next_node_ids"),
            "route": route,
            "plan_mode": plan_mode,
            "plan_origin": plan_origin,
            "observed_tool": observed_tool,
            "observed_tool_output": observed_tool_output,
            "plan_signals": plan_signals,
            "synchronization_source": "runtime_projection",
        }
        return {
            "route": "continue",
            "response_target": response_target,
            "conversation_plan": plan,
            "plan_tree_context": self._compact_conversation_plan(plan),
            "plan_graph_debug": dict(self.plan_graph_debug),
        }

    def route(self, state: AgentState) -> str:
        return str(state.get("route", "continue")).strip().lower() or "continue"

    def _project_plan(
        self,
        *,
        existing_plan: dict[str, Any],
        memory_state: dict[str, Any],
        user_input: str,
        mode: str,
        plan_origin: str,
        response_target: str,
        route: str,
        plan_signals: dict[str, Any],
        observed_tool: str,
        observed_tool_output: dict[str, Any],
    ) -> dict[str, Any]:
        plan = (
            self._create_initial_plan_graph(memory_state=memory_state, mode=mode)
            if not existing_plan
            else self._normalize_existing_plan(existing_plan=existing_plan, memory_state=memory_state, mode=mode)
        )
        previous_current = str(plan.get("current_node_id", "")).strip()
        prior_executed = previous_current if existing_plan else ""
        current = self._current_objective_from_runtime(
            memory_state=memory_state,
            previous_current=prior_executed,
            user_input=user_input,
            plan_signals=plan_signals,
        )
        if current in {"human_escalation", "transfer_to_specialist"}:
            self._ensure_handoff_branch(plan)

        markers = self._project_markers(
            plan=plan,
            memory_state=memory_state,
            previous_current=prior_executed,
            current=current,
            observed_tool=observed_tool,
            observed_tool_output=observed_tool_output,
        )
        self._apply_node_statuses(
            plan=plan,
            markers=markers,
            current=current,
            response_target=response_target,
        )

        changed = previous_current != current
        if changed or response_target != "customer" or bool(plan_signals.get("is_plan_rejection", False)):
            plan["version"] = int(plan.get("version", 1) or 1) + 1
            revisions = list(plan.get("revision_log", [])) if isinstance(plan.get("revision_log"), list) else []
            revisions.append(
                {
                    "revision": plan["version"],
                    "reason": f"runtime objective changed: {previous_current or 'initial'} -> {current}",
                    "at_utc": self._now(),
                }
            )
            plan["revision_log"] = revisions[-40:]

        plan["previous_node_id"] = previous_current or None
        plan["current_node_id"] = current
        plan["next_node_ids"] = self._pending_successors(plan=plan, current=current)
        plan["mode"] = mode
        plan["updated_from"] = plan_origin
        plan["last_response_target"] = response_target
        plan["status"] = "completed" if bool(memory_state.get("conversation_closed", False)) else "active"
        self._append_timeline_snapshot(
            plan=plan,
            update={
                "origin": plan_origin,
                "route": route,
                "response_target": response_target,
                "previous_node_id": previous_current,
                "current_node_id": current,
                "operation": "runtime_projection",
            },
        )
        return plan

    @staticmethod
    def _current_objective_from_runtime(
        *,
        memory_state: dict[str, Any],
        previous_current: str,
        user_input: str,
        plan_signals: dict[str, Any],
    ) -> str:
        if bool(memory_state.get("conversation_closed", False)) or is_conversation_termination(user_input):
            return "close_conversation"

        right_party = str(memory_state.get("right_party_status", "")).strip().lower()
        wrong_party_stage = str(memory_state.get("wrong_party_callback_stage", "")).strip().lower()
        if right_party == "wrong_party":
            return "close_conversation" if wrong_party_stage == "completed" else "wrong_party_callback"

        callback_stage = str(memory_state.get("customer_callback_stage", "")).strip().lower()
        if callback_stage in {"awaiting_callback", "scheduling", "completed"}:
            return "close_conversation" if callback_stage == "completed" else "customer_callback"

        if not bool(memory_state.get("identity_verified", False)):
            return "verify_identity"

        completed_objectives = {
            str(item).strip().lower()
            for item in memory_state.get("completed_objectives", [])
            if str(item).strip()
        } if isinstance(memory_state.get("completed_objectives"), list) else set()
        if (
            "hardship_hold_confirmation" in completed_objectives
            and str(memory_state.get("hardship_hold_stage", "")).strip().lower() == "confirmed"
        ):
            return "close_conversation"
        if (
            "installment_discount_confirmation" in completed_objectives
            and str(memory_state.get("discount_stage", "")).strip().lower() == "confirmed"
        ):
            return "close_conversation"
        if (
            "partial_payment_confirmation" in completed_objectives
            and str(memory_state.get("partial_payment_stage", "")).strip().lower() == "confirmed"
        ):
            return "close_conversation"
        if (
            "promise_to_pay_confirmation" in completed_objectives
            and str(memory_state.get("payment_commitment_type", "NONE")).strip().upper() == "PROMISE_TO_PAY"
        ):
            return "close_conversation"
        if (
            "full_payment_confirmation" in completed_objectives
            and str(memory_state.get("payment_commitment_type", "NONE")).strip().upper() == "FULL_PAYMENT"
        ):
            autopay_stage = str(memory_state.get("autopay_stage", "")).strip().lower()
            autopay_response = str(memory_state.get("autopay_response", "none")).strip().lower()
            return "close_conversation" if autopay_stage == "enabled" or autopay_response == "declined" else "autopay_offer"

        transfer = str(memory_state.get("human_transfer_status", "")).strip().lower()
        escalation = str(memory_state.get("human_escalation_status", "")).strip().lower()
        if transfer in {"pending", "transferring", "transferred"} or escalation in {"queued", "completed"}:
            return "transfer_to_specialist"

        negotiation = str(memory_state.get("negotiation_stage", "")).strip().lower()
        discount_stage = str(memory_state.get("discount_stage", "")).strip().lower()
        discount_response = str(memory_state.get("discount_response", "")).strip().lower()
        generic_options = bool(memory_state.get("generic_options_offered_after_discount", False))
        options_exhausted = negotiation == "hardship_options_exhausted" or (
            generic_options
            and (
                discount_stage in {"counter_offer", "rejected"}
                or discount_response in {"counter", "rejected"}
            )
        )
        if options_exhausted:
            return "human_escalation"
        if bool(plan_signals.get("needs_discount_specialist", False)):
            return "evaluate_assistance"
        if discount_stage in {"requested", "planning"} or (
            discount_stage in {"", "none"}
            and bool(memory_state.get("discount_requested", False))
        ):
            return "evaluate_assistance"
        if discount_stage == "confirmed":
            return (
                "close_conversation"
                if bool(memory_state.get("discount_confirmation_delivered", False))
                else "confirmation"
            )
        if discount_stage in {"offered", "accepted"}:
            return "discount_offer"
        if discount_stage in {"counter_offer", "rejected"} or discount_response in {"counter", "rejected"}:
            return "collect_payment_intent" if generic_options else "explain_dues"

        hold_stage = str(memory_state.get("hardship_hold_stage", "")).strip().lower()
        hold_response = str(memory_state.get("hold_response", "")).strip().lower()
        if hold_stage == "confirmed":
            return (
                "close_conversation"
                if bool(memory_state.get("hardship_hold_confirmation_delivered", False))
                else "confirmation"
            )
        if hold_response in {"uncertain", "rejected"}:
            return "discount_offer"
        if hold_stage in {"accepted", "created", "sms_sent"}:
            return "confirmation"
        if hold_stage == "offered":
            return "resolution_offer"

        commitment = str(memory_state.get("payment_commitment_type", "NONE")).strip().upper()
        confirmation_reason = PlanProposalGraphNode._existing_confirmation_reason(memory_state)
        promise_stage = str(memory_state.get("promise_stage", "")).strip().lower()
        if commitment == "PROMISE_TO_PAY":
            if promise_stage == "confirmed" or bool(memory_state.get("promise_confirmation_delivered", False)):
                return "close_conversation"
            if promise_stage == "followup_scheduled":
                return "confirmation"
            if promise_stage == "captured":
                return "promise_followup"
            if promise_stage in {"date_captured", "recording"}:
                return "promise_capture"
            return "promise_date"

        payment_stage = str(memory_state.get("payment_resolution_stage", "")).strip().lower()
        autopay_stage = str(memory_state.get("autopay_stage", "")).strip().lower()
        autopay_response = str(memory_state.get("autopay_response", "none")).strip().lower()
        if commitment == "FULL_PAYMENT":
            confirmation_delivered = (
                bool(memory_state.get("full_payment_confirmation_delivered", False))
                or confirmation_reason == "autopay_enabled_confirmation_delivered"
            )
            if confirmation_delivered:
                return "close_conversation" if autopay_stage == "enabled" else "autopay_offer"
            if autopay_response == "declined":
                return "close_conversation"
            if autopay_stage == "enabled":
                return "confirmation"
            if payment_stage in {"confirmed", "link_sent", "autopay_offered"}:
                return "autopay_offer"
            if payment_stage in {"link_requested", "link_created"}:
                return "full_payment_link"
            if payment_stage in {"options_offered", "link_offered"}:
                return "full_payment_options"
            return "collect_payment_intent"

        partial_stage = str(memory_state.get("partial_payment_stage", "")).strip().lower()
        if partial_stage:
            if bool(memory_state.get("partial_payment_confirmation_delivered", False)):
                return "close_conversation"
            if partial_stage == "confirmed":
                return "confirmation"
            if partial_stage in {"link_offered", "link_requested", "link_created"}:
                return "partial_link"
            if partial_stage in {"collecting_amount", "amount_invalid"}:
                return "partial_amount"

        hardship = (
            memory_state.get("hardship_context")
            if isinstance(memory_state.get("hardship_context"), dict)
            else {}
        )
        if bool(hardship.get("hardship_detected", False)):
            return (
                "resolution_offer"
                if PlanProposalGraphNode._has_eligible_premium_hold(memory_state)
                else "evaluate_assistance"
            )
        if str(memory_state.get("customer_payment_posture", "")).strip().lower() == "partial_now":
            return "partial_amount"

        if previous_current == "purpose_disclosure":
            return "collect_payment_intent"
        if previous_current not in {"", "open_and_context", "verify_identity"}:
            return previous_current
        verification_answer = bool(
            re.search(r"\b\d{4}-\d{2}-\d{2}\b", user_input)
            or re.search(r"\b\d{10,12}\b", user_input)
        )
        return "purpose_disclosure" if verification_answer else "explain_dues"

    def _project_markers(
        self,
        *,
        plan: dict[str, Any],
        memory_state: dict[str, Any],
        previous_current: str,
        current: str,
        observed_tool: str,
        observed_tool_output: dict[str, Any],
    ) -> dict[str, Any]:
        node_ids = {
            str(node.get("id", "")).strip()
            for node in plan.get("nodes", [])
            if isinstance(node, dict) and str(node.get("id", "")).strip()
        }
        existing = plan.get("step_markers") if isinstance(plan.get("step_markers"), dict) else {}
        markers: dict[str, dict[str, Any]] = {}
        now = self._now()
        for node_id in node_ids:
            raw = existing.get(node_id) if isinstance(existing.get(node_id), dict) else {}
            state = str(raw.get("state", "pending")).strip().lower()
            if state not in _VALID_STATES:
                state = "pending"
            markers[node_id] = {
                "state": state,
                "updated_at": str(raw.get("updated_at", "")) or now,
                "source": str(raw.get("source", "")) or "runtime_projection",
                "reason": str(raw.get("reason", "")),
            }

        def set_marker(node_id: str, status: str, reason: str) -> None:
            if node_id not in node_ids:
                return
            markers[node_id] = {
                "state": status,
                "updated_at": now,
                "source": "runtime_projection",
                "reason": reason,
            }

        set_marker("open_and_context", "done", "case_context_loaded")
        identity_verified = bool(memory_state.get("identity_verified", False))
        if identity_verified:
            set_marker("verify_identity", "done", "identity_verified")

        right_party = str(memory_state.get("right_party_status", "")).strip().lower()
        callback_stage = str(memory_state.get("customer_callback_stage", "")).strip().lower()
        wrong_party_stage = str(memory_state.get("wrong_party_callback_stage", "")).strip().lower()
        if right_party == "wrong_party":
            self._project_wrong_party_markers(
                set_marker=set_marker,
                completed=wrong_party_stage == "completed",
            )
        elif callback_stage in {"awaiting_callback", "scheduling", "completed"} and not identity_verified:
            set_marker("verify_identity", "skipped", "customer_requested_callback_before_verification")
        else:
            set_marker("wrong_party_callback", "skipped", "right_party_or_standard_flow")

        for node_id in node_ids:
            projection = self._objective_evidence(
                node_id=node_id,
                current=current,
                memory_state=memory_state,
            )
            if projection:
                status, reason = projection
                set_marker(node_id, status, reason)

        if previous_current and previous_current != current and previous_current in node_ids:
            if markers[previous_current]["state"] == "pending":
                set_marker(previous_current, "done", "previous_active_objective_executed")

        commitment = str(memory_state.get("payment_commitment_type", "NONE")).strip().upper()
        mutually_exclusive = {
            "FULL_PAYMENT": {
                "partial_amount",
                "partial_link",
                "promise_date",
                "promise_capture",
                "promise_followup",
            },
            "PARTIAL_PAYMENT": {
                "full_payment_options",
                "full_payment_link",
                "autopay_offer",
                "promise_date",
                "promise_capture",
                "promise_followup",
            },
            "PROMISE_TO_PAY": {
                "full_payment_options",
                "full_payment_link",
                "autopay_offer",
                "partial_amount",
                "partial_link",
            },
        }
        for node_id in mutually_exclusive.get(commitment, set()):
            if markers.get(node_id, {}).get("state") != "done":
                set_marker(node_id, "skipped", f"mutually_exclusive_{commitment.lower()}_selected")

        failed_statuses = {"failed", "error", "locked", "rejected", "denied", "invalid"}
        tool_status = str(observed_tool_output.get("status", "")).strip().lower()
        if (
            observed_tool
            and tool_status in failed_statuses
            and current in node_ids
            and self._tool_matches_node(
                node_id=current,
                node_label=self._node_label(plan, current),
                observed_tool=observed_tool,
            )
        ):
            set_marker(current, "blocked", f"tool_failed:{observed_tool}")

        # The active objective is always pending until execution supplies
        # completion evidence. This guarantees exactly one in-progress node.
        if current in node_ids and markers[current]["state"] != "blocked":
            set_marker(current, "pending", "current_runtime_objective")
        if bool(memory_state.get("conversation_closed", False)):
            set_marker("close_conversation", "done", "conversation_closed")
        plan["step_markers"] = markers
        return markers

    @staticmethod
    def _objective_evidence(
        *,
        node_id: str,
        current: str,
        memory_state: dict[str, Any],
    ) -> tuple[str, str] | None:
        identity_verified = bool(memory_state.get("identity_verified", False))
        callback_stage = str(memory_state.get("customer_callback_stage", "")).strip().lower()
        if (
            node_id == "purpose_disclosure"
            and callback_stage in {"awaiting_callback", "scheduling", "completed"}
            and not identity_verified
        ):
            return None
        if node_id == "purpose_disclosure" and current not in {
            "open_and_context",
            "verify_identity",
            "purpose_disclosure",
            "customer_callback",
        }:
            return "done", "purpose_disclosure_executed"

        hold_stage = str(memory_state.get("hardship_hold_stage", "")).strip().lower()
        hold_response = str(memory_state.get("hold_response", "")).strip().lower()
        discount_stage = str(memory_state.get("discount_stage", "")).strip().lower()
        discount_response = str(memory_state.get("discount_response", "")).strip().lower()
        discount_evidence = (
            discount_stage in {"offered", "accepted", "confirmed", "rejected", "counter_offer"}
            or discount_response in {"accepted", "rejected", "counter"}
        )
        hold_evidence = hold_stage in {
            "offered",
            "accepted",
            "created",
            "sms_sent",
            "confirmed",
            "superseded",
        }
        if node_id == "discovery_empathy" and (hold_evidence or discount_evidence):
            return "done", "hardship_acknowledged"
        if node_id == "resolution_offer" and (
            hold_stage in {"accepted", "created", "sms_sent", "confirmed", "superseded"}
            or hold_response in {"accepted", "uncertain", "rejected"}
        ):
            return "done", "hold_option_presented"
        if node_id == "assess_after_hold":
            if hold_response in {"uncertain", "rejected"}:
                return "done", "post_hold_ability_assessed"
            if hold_stage == "superseded" and discount_evidence:
                return "done", "hold_assessment_completed_before_discount"
            if hold_evidence and discount_evidence:
                return "done", "discount_progress_proves_hold_assessment_completed"
            if discount_evidence and not hold_evidence:
                return "skipped", "discount_selected_without_hold_assessment"
        if node_id == "discount_offer" and (
            discount_stage in {"accepted", "confirmed", "rejected", "counter_offer"}
            or discount_response in {"accepted", "rejected", "counter"}
        ):
            return "done", "discount_offer_executed"

        commitment = str(memory_state.get("payment_commitment_type", "NONE")).strip().upper()
        partial_stage = str(memory_state.get("partial_payment_stage", "")).strip().lower()
        partial_details = (
            memory_state.get("partial_payment_details")
            if isinstance(memory_state.get("partial_payment_details"), dict)
            else {}
        )
        if node_id == "collect_payment_intent" and (
            commitment in {"FULL_PAYMENT", "PARTIAL_PAYMENT", "PROMISE_TO_PAY"}
            or partial_stage in {"collecting_amount", "link_offered", "link_requested", "link_created", "confirmed"}
        ):
            return "done", "payment_intent_captured"
        if node_id == "partial_amount" and (
            partial_details.get("partial_payment_amount") not in {None, ""}
            or partial_stage in {"link_offered", "link_requested", "link_created", "confirmed"}
        ):
            return "done", "partial_amount_validated"
        partial_sms = (
            partial_details.get("sms_confirmation")
            if isinstance(partial_details.get("sms_confirmation"), dict)
            else {}
        )
        if node_id == "partial_link" and (
            partial_stage == "confirmed"
            or (
                str(partial_details.get("payment_reference_id", "")).strip()
                and str(partial_sms.get("status", "")).strip().lower() == "sent"
            )
        ):
            return "done", "partial_payment_link_sent"

        payment_stage = str(memory_state.get("payment_resolution_stage", "")).strip().lower()
        full_details = (
            memory_state.get("full_payment_details")
            if isinstance(memory_state.get("full_payment_details"), dict)
            else {}
        )
        if node_id == "full_payment_options" and commitment == "FULL_PAYMENT" and payment_stage in {
            "link_requested",
            "link_created",
            "confirmed",
            "link_sent",
            "autopay_offered",
        }:
            return "done", "full_payment_method_offered"
        full_sms = (
            full_details.get("sms_confirmation")
            if isinstance(full_details.get("sms_confirmation"), dict)
            else {}
        )
        if node_id == "full_payment_link" and (
            payment_stage in {"confirmed", "link_sent", "autopay_offered"}
            or (
                str(full_details.get("payment_reference_id", "")).strip()
                and str(full_sms.get("status", "")).strip().lower() == "sent"
            )
        ):
            return "done", "full_payment_link_sent"

        autopay_stage = str(memory_state.get("autopay_stage", "")).strip().lower()
        autopay_response = str(memory_state.get("autopay_response", "none")).strip().lower()
        disposition = str(memory_state.get("final_disposition", "")).strip().upper()
        if node_id == "autopay_offer":
            if autopay_stage == "enabled" or disposition == "AUTOPAY_ENABLED":
                return "done", "autopay_enabled"
            if autopay_response == "declined":
                return "skipped", "autopay_declined"

        promise_stage = str(memory_state.get("promise_stage", "")).strip().lower()
        promise_details = (
            memory_state.get("promise_to_pay_details")
            if isinstance(memory_state.get("promise_to_pay_details"), dict)
            else {}
        )
        if node_id == "promise_date" and promise_stage in {
            "date_captured",
            "recording",
            "captured",
            "followup_scheduled",
            "confirmed",
        }:
            return "done", "promise_date_captured"
        if node_id == "promise_capture" and (
            str(memory_state.get("promise_reference", "")).strip()
            or promise_stage in {"captured", "followup_scheduled", "confirmed"}
        ):
            return "done", "promise_recorded"
        followup = (
            promise_details.get("followup_schedule")
            if isinstance(promise_details.get("followup_schedule"), dict)
            else {}
        )
        if node_id == "promise_followup" and (
            str(followup.get("schedule_id", "")).strip()
            or promise_stage in {"followup_scheduled", "confirmed"}
            or disposition == "PROMISE_TO_PAY_SCHEDULED"
        ):
            return "done", "promise_followup_scheduled"

        if node_id == "customer_callback":
            outbound_status = str(memory_state.get("outbound_callback_status", "")).strip().lower()
            if callback_stage == "completed" and outbound_status == "scheduled":
                return "done", "customer_callback_scheduled"

        completed_objectives = {
            str(item).strip().lower()
            for item in memory_state.get("completed_objectives", [])
            if str(item).strip()
        } if isinstance(memory_state.get("completed_objectives"), list) else set()
        if node_id == "confirmation" and completed_objectives.intersection(
            {
                "hardship_hold_confirmation",
                "installment_discount_confirmation",
                "partial_payment_confirmation",
                "full_payment_confirmation",
                "promise_to_pay_confirmation",
            }
        ):
            return "done", "confirmation_response_rendered"

        escalation = str(memory_state.get("human_escalation_status", "")).strip().lower()
        transfer = str(memory_state.get("human_transfer_status", "")).strip().lower()
        handoff_started = escalation in {"queued", "completed"} or transfer in {
            "pending",
            "transferring",
            "transferred",
        }
        if node_id == "human_escalation" and handoff_started:
            return "done", "human_escalation_queued"
        if node_id == "transfer_to_specialist" and transfer == "transferred":
            return "done", "human_transfer_completed"
        if node_id == "confirmation" and (
            handoff_started or current in {"human_escalation", "transfer_to_specialist"}
        ):
            return "skipped", "handoff_replaces_standard_confirmation"
        return None

    @staticmethod
    def _project_wrong_party_markers(*, set_marker: Any, completed: bool) -> None:
        set_marker("verify_identity", "skipped", "wrong_party_no_verification")
        for node_id in (
            "purpose_disclosure",
            "discovery_empathy",
            "resolution_offer",
            "assess_after_hold",
            "discount_offer",
            "confirmation",
            "explain_dues",
            "collect_payment_intent",
            "evaluate_assistance",
            "resolve_outcome",
        ):
            set_marker(node_id, "skipped", "wrong_party_privacy_branch")
        if completed:
            set_marker("wrong_party_callback", "done", "wrong_party_callback_confirmed")

    @staticmethod
    def _apply_node_statuses(
        *,
        plan: dict[str, Any],
        markers: dict[str, dict[str, Any]],
        current: str,
        response_target: str,
    ) -> None:
        for node in plan.get("nodes", []):
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id", "")).strip()
            marker = markers.get(node_id, {})
            marker_state = str(marker.get("state", "pending")).strip().lower()
            if node_id == current and marker_state != "blocked":
                node["status"] = "in_progress"
                if response_target == "self":
                    node["owner"] = "collection_agent"
            elif marker_state in _TERMINAL_STATES:
                node["status"] = marker_state
            else:
                node["status"] = "pending"

    @staticmethod
    def _create_initial_plan_graph(*, memory_state: dict[str, Any], mode: str) -> dict[str, Any]:
        case_id = str(memory_state.get("active_case_id", "COLL-1001")).strip().upper() or "COLL-1001"
        nodes = [
            {"id": node_id, "label": label, "owner": owner, "status": "pending"}
            for node_id, label, owner in PlanProposalGraphNode._base_node_specs()
        ]
        return {
            "plan_id": f"plan-{case_id}",
            "version": 1,
            "status": "active",
            "mode": mode,
            "objective": "Move borrower conversation to payment, promise-to-pay, or compliant follow-up.",
            "root_node_id": "open_and_context",
            "current_node_id": "verify_identity",
            "previous_node_id": None,
            "next_node_ids": [],
            "nodes": nodes,
            "edges": PlanProposalGraphNode._base_edges(),
            "step_markers": {},
            "timeline": [],
            "timeline_snapshots": [],
            "revision_log": [],
            "updated_from": "initial",
            "last_response_target": "customer",
        }

    @staticmethod
    def _normalize_existing_plan(
        *,
        existing_plan: dict[str, Any],
        memory_state: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        plan = dict(existing_plan)
        existing_nodes = {
            str(node.get("id", "")).strip(): dict(node)
            for node in plan.get("nodes", [])
            if isinstance(node, dict) and str(node.get("id", "")).strip()
        }
        for node_id, label, owner in PlanProposalGraphNode._base_node_specs():
            existing_nodes.setdefault(
                node_id,
                {"id": node_id, "label": label, "owner": owner, "status": "pending"},
            )
        plan["nodes"] = list(existing_nodes.values())

        edge_keys: set[tuple[str, str, str]] = set()
        edges: list[dict[str, str]] = []
        for edge in [*plan.get("edges", []), *PlanProposalGraphNode._base_edges()]:
            if not isinstance(edge, dict):
                continue
            normalized = {
                "from": str(edge.get("from", "")).strip(),
                "to": str(edge.get("to", "")).strip(),
                "condition": str(edge.get("condition", "")).strip(),
            }
            key = (normalized["from"], normalized["to"], normalized["condition"])
            if normalized["from"] and normalized["to"] and key not in edge_keys:
                edges.append(normalized)
                edge_keys.add(key)
        plan["edges"] = edges
        plan.setdefault(
            "plan_id",
            f"plan-{str(memory_state.get('active_case_id', 'COLL-1001')).strip().upper()}",
        )
        plan.setdefault("version", 1)
        plan.setdefault("status", "active")
        plan.setdefault("objective", "Move borrower conversation to payment resolution.")
        plan.setdefault("root_node_id", "open_and_context")
        plan.setdefault("current_node_id", "verify_identity")
        plan.setdefault("step_markers", {})
        plan.setdefault("timeline", [])
        plan.setdefault("timeline_snapshots", [])
        plan.setdefault("revision_log", [])
        plan["mode"] = mode
        return plan

    @staticmethod
    def _base_node_specs() -> list[tuple[str, str, str]]:
        return [
            ("open_and_context", "Initialize case context", "collection_agent"),
            ("verify_identity", "Verify customer identity", "customer"),
            ("wrong_party_callback", "Arrange privacy-safe callback", "collection_agent"),
            ("purpose_disclosure", "Disclose call purpose and overdue installment", "collection_agent"),
            ("discovery_empathy", "Understand and acknowledge customer situation", "collection_agent"),
            ("resolution_offer", "Present eligible resolution option", "collection_agent"),
            ("assess_after_hold", "Assess ability to resume after hold", "customer"),
            ("discount_offer", "Present eligible installment discount", "collection_agent"),
            ("explain_dues", "Explain standard payment options", "customer"),
            ("collect_payment_intent", "Collect payment intent", "customer"),
            ("partial_amount", "Identify and validate partial-payment amount", "customer"),
            ("partial_link", "Create and send secure partial-payment link", "collection_agent"),
            ("full_payment_options", "Offer full-payment method", "collection_agent"),
            ("full_payment_link", "Create and send secure full-payment link", "collection_agent"),
            ("autopay_offer", "Offer auto-pay setup", "customer"),
            ("promise_date", "Capture promised payment date", "customer"),
            ("promise_capture", "Record promise-to-pay commitment", "collection_agent"),
            ("promise_followup", "Schedule promise reminder and payment link", "collection_agent"),
            ("customer_callback", "Schedule customer-requested callback", "collection_agent"),
            ("evaluate_assistance", "Evaluate discount/restructure assistance", "collection_agent"),
            ("resolve_outcome", "Finalize payment, promise, or follow-up", "customer"),
            ("confirmation", "Confirm agreed outcome and reference", "collection_agent"),
            ("close_conversation", "Close conversation", "collection_agent"),
        ]

    @staticmethod
    def _base_edges() -> list[dict[str, str]]:
        raw = [
            ("open_and_context", "verify_identity", "case_context_ready"),
            ("verify_identity", "purpose_disclosure", "identity_verified"),
            ("verify_identity", "wrong_party_callback", "wrong_party_detected"),
            ("verify_identity", "customer_callback", "customer_unavailable"),
            ("purpose_disclosure", "discovery_empathy", "customer_situation_shared"),
            ("purpose_disclosure", "explain_dues", "standard_resolution_requested"),
            ("purpose_disclosure", "partial_amount", "partial_payment_available"),
            ("purpose_disclosure", "customer_callback", "customer_unavailable"),
            ("discovery_empathy", "resolution_offer", "eligible_assistance_found"),
            ("resolution_offer", "confirmation", "hold_accepted"),
            ("resolution_offer", "assess_after_hold", "customer_unsure_after_hold"),
            ("resolution_offer", "customer_callback", "customer_unavailable"),
            ("assess_after_hold", "discount_offer", "discount_eligible"),
            ("discount_offer", "confirmation", "discount_accepted"),
            ("discount_offer", "explain_dues", "discount_rejected"),
            ("explain_dues", "collect_payment_intent", "options_explained"),
            ("collect_payment_intent", "partial_amount", "partial_payment"),
            ("partial_amount", "partial_link", "amount_validated"),
            ("partial_link", "confirmation", "link_sent"),
            ("collect_payment_intent", "full_payment_options", "pay_now"),
            ("full_payment_options", "full_payment_link", "payment_link_requested"),
            ("full_payment_link", "confirmation", "link_sent"),
            ("confirmation", "autopay_offer", "autopay_offered"),
            ("autopay_offer", "confirmation", "autopay_accepted"),
            ("autopay_offer", "close_conversation", "autopay_declined_or_later"),
            ("collect_payment_intent", "promise_date", "promise_to_pay"),
            ("promise_date", "promise_capture", "valid_date_captured"),
            ("promise_capture", "promise_followup", "promise_recorded"),
            ("promise_followup", "confirmation", "followup_scheduled"),
            ("collect_payment_intent", "customer_callback", "customer_unavailable"),
            ("collect_payment_intent", "evaluate_assistance", "cannot_pay_full"),
            ("evaluate_assistance", "resolve_outcome", "assistance_ready"),
            ("resolve_outcome", "confirmation", "outcome_ready"),
            ("customer_callback", "close_conversation", "callback_scheduled"),
            ("wrong_party_callback", "close_conversation", "callback_confirmed"),
            ("confirmation", "close_conversation", "outcome_confirmed"),
        ]
        return [{"from": src, "to": dst, "condition": condition} for src, dst, condition in raw]

    @staticmethod
    def _ensure_handoff_branch(plan: dict[str, Any]) -> None:
        node_ids = {
            str(node.get("id", "")).strip()
            for node in plan.get("nodes", [])
            if isinstance(node, dict)
        }
        additions = [
            ("human_escalation", "Queue human specialist escalation"),
            ("transfer_to_specialist", "Transfer call to specialist"),
        ]
        for node_id, label in additions:
            if node_id not in node_ids:
                plan["nodes"].append(
                    {
                        "id": node_id,
                        "label": label,
                        "owner": "collection_agent",
                        "status": "pending",
                    }
                )
                node_ids.add(node_id)
        edge_keys = {
            (str(edge.get("from", "")).strip(), str(edge.get("to", "")).strip())
            for edge in plan.get("edges", [])
            if isinstance(edge, dict)
        }
        for source in (
            "resolution_offer",
            "discount_offer",
            "evaluate_assistance",
            "resolve_outcome",
        ):
            if (source, "human_escalation") not in edge_keys:
                plan["edges"].append(
                    {
                        "from": source,
                        "to": "human_escalation",
                        "condition": "runtime_options_exhausted",
                    }
                )
        if ("human_escalation", "transfer_to_specialist") not in edge_keys:
            plan["edges"].append(
                {
                    "from": "human_escalation",
                    "to": "transfer_to_specialist",
                    "condition": "escalation_queued",
                }
            )

    @staticmethod
    def _has_eligible_premium_hold(memory_state: dict[str, Any]) -> bool:
        context = (
            memory_state.get("active_collection_context")
            if isinstance(memory_state.get("active_collection_context"), dict)
            else {}
        )
        case = context.get("case") if isinstance(context.get("case"), dict) else {}
        loan_id = str(case.get("loan_id", memory_state.get("active_loan_id", ""))).strip().upper()
        hardship = (
            memory_state.get("hardship_context")
            if isinstance(memory_state.get("hardship_context"), dict)
            else {}
        )
        reason = str(hardship.get("hardship_reason", memory_state.get("hardship_reason", ""))).strip().lower()
        programs = memory_state.get("assistance_programs") if isinstance(memory_state.get("assistance_programs"), list) else []
        for program in programs:
            if not isinstance(program, dict) or str(program.get("program_type", "")).strip().lower() != "premium_hold":
                continue
            loans = {
                str(item).strip().upper()
                for item in program.get("eligible_loan_ids", [])
                if str(item).strip()
            } if isinstance(program.get("eligible_loan_ids"), list) else set()
            reasons = {
                str(item).strip().lower()
                for item in program.get("hardship_reasons", [])
                if str(item).strip()
            } if isinstance(program.get("hardship_reasons"), list) else set()
            if loans and loan_id not in loans:
                continue
            if reasons and reason not in reasons:
                continue
            return True
        return False

    @staticmethod
    def _overlay_wrong_party_state(*, memory_state: dict[str, Any], user_input: str) -> None:
        if bool(memory_state.get("identity_verified", False)):
            return
        right_party = str(memory_state.get("right_party_status", "")).strip().lower()
        if right_party == "wrong_party":
            stage = str(memory_state.get("wrong_party_callback_stage", "")).strip().lower()
            if stage == "awaiting_callback" and looks_like_callback_time(user_input):
                callback_time = extract_callback_time(user_input)
                if callback_time:
                    memory_state["wrong_party_callback_stage"] = "completed"
                    memory_state["wrong_party_callback_time"] = callback_time
            return
        if not is_right_party_denial(
            user_input,
            awaiting_confirmation=right_party in {"", "awaiting_confirmation"},
        ):
            return
        callback_time = extract_callback_time(user_input) if looks_like_callback_time(user_input) else ""
        normalized = re.sub(r"\s+", " ", user_input.strip().lower())
        memory_state["right_party_status"] = "wrong_party"
        memory_state["wrong_party_callback_stage"] = (
            "completed"
            if callback_time
            else "privacy_notice_given"
            if normalized in {"no", "nope", "nah"}
            else "awaiting_callback"
        )
        memory_state["wrong_party_callback_time"] = callback_time or None

    @staticmethod
    def _existing_confirmation_reason(memory_state: dict[str, Any]) -> str:
        plan = (
            memory_state.get("active_conversation_plan")
            if isinstance(memory_state.get("active_conversation_plan"), dict)
            else {}
        )
        markers = plan.get("step_markers") if isinstance(plan.get("step_markers"), dict) else {}
        marker = markers.get("confirmation") if isinstance(markers.get("confirmation"), dict) else {}
        return str(marker.get("reason", "")).strip().lower()

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        stop = {"and", "or", "the", "a", "an", "to", "of", "for", "with", "customer", "agent"}
        return {
            token
            for token in re.findall(r"[a-z0-9]+", str(text).lower())
            if token and token not in stop
        }

    def _tool_matches_node(self, *, node_id: str, node_label: str, observed_tool: str) -> bool:
        tool_tokens = self._tokenize(observed_tool)
        node_tokens = self._tokenize(node_id) | self._tokenize(node_label)
        return bool(tool_tokens and node_tokens and tool_tokens.intersection(node_tokens))

    @staticmethod
    def _node_label(plan: dict[str, Any], node_id: str) -> str:
        for node in plan.get("nodes", []):
            if isinstance(node, dict) and str(node.get("id", "")).strip() == node_id:
                return str(node.get("label", node_id)).strip() or node_id
        return node_id

    @staticmethod
    def _pending_successors(*, plan: dict[str, Any], current: str) -> list[str]:
        statuses = {
            str(node.get("id", "")).strip(): str(node.get("status", "pending")).strip().lower()
            for node in plan.get("nodes", [])
            if isinstance(node, dict)
        }
        result: list[str] = []
        for edge in plan.get("edges", []):
            if not isinstance(edge, dict) or str(edge.get("from", "")).strip() != current:
                continue
            destination = str(edge.get("to", "")).strip()
            if destination and statuses.get(destination) == "pending" and destination not in result:
                result.append(destination)
        return result

    @staticmethod
    def _compact_conversation_plan(plan: dict[str, Any]) -> dict[str, Any]:
        nodes = [
            {
                "id": str(node.get("id", "")).strip(),
                "label": str(node.get("label", "")).strip(),
                "status": str(node.get("status", "")).strip(),
                "owner": str(node.get("owner", "")).strip(),
            }
            for node in plan.get("nodes", [])
            if isinstance(node, dict)
        ]
        edges = [
            {
                "from": str(edge.get("from", "")).strip(),
                "to": str(edge.get("to", "")).strip(),
                "condition": str(edge.get("condition", "")).strip(),
            }
            for edge in plan.get("edges", [])
            if isinstance(edge, dict)
        ]
        markers = plan.get("step_markers") if isinstance(plan.get("step_markers"), dict) else {}
        return {
            "plan_id": str(plan.get("plan_id", "")).strip(),
            "version": int(plan.get("version", 1) or 1),
            "status": str(plan.get("status", "active")).strip(),
            "current_node_id": str(plan.get("current_node_id", "")).strip(),
            "next_node_ids": list(plan.get("next_node_ids", [])),
            "nodes": nodes,
            "edges": edges,
            "step_markers": {
                str(node_id): str(raw.get("state", "pending")).strip()
                for node_id, raw in markers.items()
                if isinstance(raw, dict)
            },
        }

    @staticmethod
    def _append_timeline_snapshot(*, plan: dict[str, Any], update: dict[str, Any]) -> None:
        now = PlanProposalGraphNode._now()
        timeline = list(plan.get("timeline", [])) if isinstance(plan.get("timeline"), list) else []
        timeline.append(
            {
                "at_utc": now,
                "version": int(plan.get("version", 1) or 1),
                "status": str(plan.get("status", "active")),
                "current_node_id": str(plan.get("current_node_id", "")),
                "next_node_ids": list(plan.get("next_node_ids", [])),
                "update": dict(update),
            }
        )
        plan["timeline"] = timeline[-40:]

        snapshot_plan = {
            "plan_id": str(plan.get("plan_id", "")),
            "version": int(plan.get("version", 1) or 1),
            "status": str(plan.get("status", "active")),
            "mode": str(plan.get("mode", "strict_collections")),
            "objective": str(plan.get("objective", "")),
            "root_node_id": str(plan.get("root_node_id", "")),
            "current_node_id": str(plan.get("current_node_id", "")),
            "previous_node_id": plan.get("previous_node_id"),
            "next_node_ids": list(plan.get("next_node_ids", [])),
            "nodes": [dict(node) for node in plan.get("nodes", []) if isinstance(node, dict)],
            "edges": [dict(edge) for edge in plan.get("edges", []) if isinstance(edge, dict)],
            "step_markers": dict(plan.get("step_markers", {})),
            "updated_from": str(plan.get("updated_from", "")),
            "last_response_target": str(plan.get("last_response_target", "")),
        }
        snapshots = (
            list(plan.get("timeline_snapshots", []))
            if isinstance(plan.get("timeline_snapshots"), list)
            else []
        )
        snapshots.append(
            {
                "at_utc": now,
                "version": int(plan.get("version", 1) or 1),
                "status": str(plan.get("status", "active")),
                "current_node_id": str(plan.get("current_node_id", "")),
                "update": dict(update),
                "plan": snapshot_plan,
            }
        )
        plan["timeline_snapshots"] = snapshots[-80:]

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
