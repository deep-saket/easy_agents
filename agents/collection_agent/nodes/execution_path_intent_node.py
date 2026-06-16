"""Execution-path intent node for collection agent."""

from __future__ import annotations

import re
from typing import Any

from agents.collection_agent.nodes.callback_time_extractor import extract_callback_time
from agents.collection_agent.nodes.collection_intent_node import CollectionIntentNode
from src.nodes.types import AgentState


class ExecutionPathIntentNode(CollectionIntentNode):
    """Intent node dedicated to execution-path routing.

    State Keys Read:
    - `user_input`
    - `message_source`
    - `conversation_phase`
    - `case_id`
    - `user_id`
    - `conversation_plan`
    - `observations`
    - `observation` (latest compatibility mirror)
    - `verification_verified_fields`
    - `verification_missing_fields`
    - `verification_entities`
    - `extracted_entities_turn`
    - `memory` (reads `memory.state` for plan and verification context)

    State Keys Write:
    - `execution_path_intent`
    - `intent` (compatibility mirror)
    - `prompt`
    - `system_prompt`
    - `llm_response`
    - `llm_error`
    - `llm_status`
    - `fallback_reason` (optional)
    """

    def __init__(
        self,
        *,
        llm: Any | None,
        allow_deterministic_fallback: bool,
        system_prompt: str,
        user_prompt: str,
    ) -> None:
        super().__init__(
            llm=llm,
            allow_deterministic_fallback=allow_deterministic_fallback,
            allow_rate_limit_fallback=False,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_key="execution_path_intent",
            intent_labels=["need_memory", "need_tool"],
            default_intent="need_tool",
            default_confidence=0.4,
            route_map={
                "need_memory": "need_memory",
                "need_tool": "need_tool",
                "unknown": "need_tool",
            },
            default_route="need_tool",
            fallback_keyword_map={},
        )

    def _build_context_for_intent(self, state: AgentState) -> dict[str, Any]:
        memory_state = self._get_memory_state(state)
        plan = memory_state.get("active_conversation_plan")
        if not isinstance(plan, dict):
            plan = state.get("conversation_plan") if isinstance(state.get("conversation_plan"), dict) else {}
        current_node_id = str(plan.get("current_node_id", "")).strip() if isinstance(plan, dict) else ""
        current_node_label = ""
        if current_node_id and isinstance(plan, dict):
            for node in plan.get("nodes", []):
                if isinstance(node, dict) and str(node.get("id", "")).strip() == current_node_id:
                    current_node_label = str(node.get("label", "")).strip()
                    break

        observation = None
        observations = state.get("observations")
        if isinstance(observations, list):
            for item in reversed(observations):
                if isinstance(item, dict):
                    observation = item
                    break
        if observation is None:
            observation = state.get("observation")
        obs_payload: dict[str, Any] = {}
        if isinstance(observation, dict):
            tool_phase = observation.get("tool_phase")
            if isinstance(tool_phase, dict):
                obs_payload = tool_phase
            else:
                obs_payload = observation

        user_text = str(state.get("user_input", "")).strip()
        identity_verified = bool(state.get("identity_verified", memory_state.get("identity_verified", False)))
        required_raw = memory_state.get("active_verification_required_fields")
        required_fields = (
            {str(x).strip().lower() for x in required_raw if str(x).strip()}
            if isinstance(required_raw, list)
            else {"dob", "phone"}
        )
        verified_raw = state.get("verification_verified_fields") or memory_state.get("verification_verified_fields")
        verified_fields = (
            {str(x).strip().lower() for x in verified_raw if str(x).strip()}
            if isinstance(verified_raw, list)
            else set()
        )
        missing_by_verified = required_fields - verified_fields
        missing_raw = state.get("verification_missing_fields") or memory_state.get("verification_missing_fields")
        missing_by_state = (
            {str(x).strip().lower() for x in missing_raw if str(x).strip()}
            if isinstance(missing_raw, list)
            else set()
        )
        missing = missing_by_verified or missing_by_state

        turn_entities_raw = state.get("extracted_entities_turn")
        if not isinstance(turn_entities_raw, dict):
            turn_entities_raw = memory_state.get("extracted_entities_turn", {})
        turn_entities = dict(turn_entities_raw) if isinstance(turn_entities_raw, dict) else {}
        provided_turn_fields = {
            str(key).strip().lower()
            for key, value in turn_entities.items()
            if str(key).strip() and str(value).strip()
        }
        obvious_fields = self._detect_obvious_verification_fields(user_text)
        verification_fields = {"dob", "phone"}
        verification_provided = sorted(
            [field for field in (provided_turn_fields | obvious_fields) if field in verification_fields]
        )
        missing_provided = sorted([field for field in verification_provided if field in missing])
        routing_hint = "decide" if ((not identity_verified) and missing_provided) else "plan"
        routing_reason = (
            "verification evidence for missing fields present in current turn"
            if routing_hint == "decide"
            else "no missing verification evidence in current turn"
        )
        observation_status = obs_payload.get("status")
        if observation_status is None and isinstance(obs_payload.get("output"), dict):
            observation_status = obs_payload.get("output", {}).get("status")
        return {
            "message_source": state.get("message_source") or memory_state.get("last_message_source"),
            "conversation_phase": state.get("conversation_phase"),
            "active_case_id": state.get("case_id") or memory_state.get("active_case_id"),
            "active_user_id": state.get("user_id") or memory_state.get("active_user_id"),
            "identity_verified": identity_verified,
            "conversation_mode": state.get("conversation_mode") or memory_state.get("conversation_mode"),
            "negotiation_stage": state.get("negotiation_stage") or memory_state.get("negotiation_stage"),
            "customer_payment_posture": state.get("customer_payment_posture")
            or memory_state.get("customer_payment_posture"),
            "hardship_context": state.get("hardship_context") or memory_state.get("hardship_context"),
            "response_mode": state.get("response_mode") or memory_state.get("response_mode"),
            "active_dialogue_owner": state.get("active_dialogue_owner") or memory_state.get("active_dialogue_owner"),
            "verification_missing_fields": sorted(missing),
            "verification_verified_fields": sorted(verified_fields),
            "verification_entities": state.get("verification_entities") or memory_state.get("verification_entities"),
            "extracted_entities_turn": turn_entities,
            "active_verification_required_fields": sorted(required_fields),
            "plan_current_node_id": current_node_id,
            "plan_current_node_label": current_node_label,
            "observation_tool_name": obs_payload.get("tool_name"),
            "observation_status": observation_status,
            "observation_output": obs_payload.get("output") if isinstance(obs_payload.get("output"), dict) else {},
            "last_agent_response": memory_state.get("last_agent_response"),
            "last_response_target": memory_state.get("last_response_target"),
            "turn_index": memory_state.get("turn_index"),
            "verification_provided_fields_turn": verification_provided,
            "verification_obvious_evidence_fields_turn": sorted(obvious_fields),
            "verification_missing_fields_provided_turn": missing_provided,
            "verification_routing_hint": routing_hint,
            "verification_routing_reason": routing_reason,
        }

    def _apply_node_specific_pre_rule(
        self,
        *,
        state: AgentState,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        memory_state = self._get_memory_state(state)
        right_party_status = str(memory_state.get("right_party_status", "")).strip().lower()
        lowered = str(state.get("user_input", "")).lower()
        if (
            str(memory_state.get("partial_payment_stage", "")).strip().lower() == "link_offered"
            and self._is_affirmative(lowered)
        ):
            return {
                "skip_llm": True,
                "reason": "Accepted partial-payment link requires creation and SMS delivery.",
                "intent": {
                    "intent": "need_tool",
                    "confidence": 1.0,
                    "reason": "Create the partial-payment link.",
                },
            }
        if (
            str(memory_state.get("hardship_hold_stage", "")).strip().lower() == "offered"
            and str(memory_state.get("hold_response", "")).strip().lower() == "uncertain"
        ):
            return {
                "skip_llm": True,
                "reason": "Post-hold uncertainty requires installment discount evaluation.",
                "intent": {
                    "intent": "need_tool",
                    "confidence": 1.0,
                    "reason": "Evaluate the configured installment discount.",
                },
            }
        if (
            str(memory_state.get("discount_stage", "")).strip().lower() in {"offered", "accepted"}
            and str(memory_state.get("discount_response", "")).strip().lower() == "accepted"
        ):
            return {
                "skip_llm": True,
                "reason": "Accepted installment discount requires application and notification tools.",
                "intent": {
                    "intent": "need_tool",
                    "confidence": 1.0,
                    "reason": "Apply the accepted installment discount.",
                },
            }
        if (
            str(memory_state.get("hardship_hold_stage", "")).strip().lower() == "offered"
            and not self._has_active_discount_branch(memory_state)
            and str(memory_state.get("hold_response", "")).strip().lower() == "accepted"
        ):
            return {
                "skip_llm": True,
                "reason": "Accepted premium hold requires creation and notification tools.",
                "intent": {
                    "intent": "need_tool",
                    "confidence": 1.0,
                    "reason": "Create the hold and send confirmation before responding.",
                },
            }
        if right_party_status == "wrong_party" and "callback" in lowered and any(
            token in lowered for token in ("cancel", "remove", "do not call", "don't call")
        ):
            return {
                "skip_llm": True,
                "reason": "Callback cancellation requires tool execution.",
                "intent": {
                    "intent": "need_tool",
                    "confidence": 1.0,
                    "reason": "Cancel the queued outbound callback.",
                },
            }
        if right_party_status == "wrong_party" and extract_callback_time(
            str(state.get("user_input", "")),
            llm=self.llm,
        ):
            return {
                "skip_llm": True,
                "reason": "Wrong-party callback time requires scheduler tool execution.",
                "intent": {
                    "intent": "need_tool",
                    "confidence": 1.0,
                    "reason": "Schedule the requested outbound callback.",
                },
            }

        identity_verified = bool(context.get("identity_verified", False))
        missing_provided = context.get("verification_missing_fields_provided_turn")
        if identity_verified or not isinstance(missing_provided, list) or not missing_provided:
            return None
        # Execution-path-specific pre-rule: if missing verification evidence is present this turn,
        # skip classifier and route to need_tool so verify_dob/verify_mobile can run immediately.
        return {
            "skip_llm": True,
            "reason": "Execution-path pre-rule: missing verification field evidence detected this turn.",
            "intent": {
                "intent": "need_tool",
                "confidence": 0.98,
                "reason": "Verification evidence present for missing field; route to tool execution.",
            },
        }

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

    def _apply_node_specific_intent_override(
        self,
        *,
        intent: dict[str, Any],
        state: AgentState,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        # Post-override currently not needed for execution-path.
        return intent

    @staticmethod
    def _detect_obvious_verification_fields(text: str) -> set[str]:
        lowered = str(text or "").lower()
        fields: set[str] = set()
        if re.search(r"\b(19|20)\d{2}-\d{2}-\d{2}\b", lowered):
            fields.add("dob")
        digits = re.sub(r"\D", "", lowered)
        if len(digits) >= 10:
            fields.add("phone")
        return fields
