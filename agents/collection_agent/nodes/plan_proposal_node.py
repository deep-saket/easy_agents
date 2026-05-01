"""Plan proposal node for hardship negotiation loop."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from src.nodes.base import BaseGraphNode
from src.nodes.types import AgentState, NodeUpdate


@dataclass(slots=True)
class PlanProposalNode(BaseGraphNode):
    """Injects plan proposal/revision tool calls when hardship negotiation is active."""

    llm: Any | None = None

    def execute(self, state: AgentState) -> NodeUpdate:
        self._record_llm_usage(state, node_name="plan_proposal")
        memory = state.get("memory")
        memory_state = dict(getattr(memory, "state", {})) if memory is not None else {}
        mode = str(memory_state.get("mode", "strict_collections"))
        routing_context = state.get("routing_context") if isinstance(state.get("routing_context"), dict) else {}
        plan_origin = str(routing_context.get("plan_origin", "react"))
        observation = state.get("observation")
        user_input = str(state.get("user_input", ""))

        if isinstance(observation, dict) and isinstance(observation.get("tool_phase"), dict):
            observation = observation.get("tool_phase")
        observed_tool = str(observation.get("tool_name", "")) if isinstance(observation, dict) else ""
        output = observation.get("output", {}) if isinstance(observation, dict) else {}

        if bool(memory_state.get("agent_loop_blocked", False)):
            if memory is not None:
                memory.set_state(agent_loop_blocked=False)
            decision = SimpleNamespace(
                thought="Agent loop guard triggered.",
                tool_call=None,
                respond_directly=True,
                response_text=(
                    "I have been running internal planning loops for too long on this request. "
                    "Please confirm one concrete next step (pay now, ask for plan revision, or schedule follow-up)."
                ),
                done=True,
            )
            return {"route": "continue", "decision": decision, "response_target": "customer"}

        if self._is_conversation_termination(user_input):
            decision = SimpleNamespace(
                thought="Detected conversation termination intent.",
                tool_call=None,
                respond_directly=True,
                response_text="Thank you. I am closing this conversation now.",
                done=True,
            )
            return {
                "route": "continue",
                "decision": decision,
                "response_target": "customer",
                "additional_targets": ["collection_memory_helper_agent"],
                "memory_helper_trigger": {
                    "reason": "conversation_termination",
                    "final_user_message": user_input,
                },
            }

        discount_recommendation = memory_state.get("discount_recommendation")
        if isinstance(discount_recommendation, dict) and discount_recommendation:
            response_text = self._build_discount_offer_response(discount_recommendation)
            if memory is not None:
                memory.set_state(discount_recommendation=None)
            decision = SimpleNamespace(
                thought="Converted discount specialist output into borrower-facing recommendation.",
                tool_call=None,
                respond_directly=True,
                response_text=response_text,
                done=True,
            )
            return {"route": "continue", "decision": decision, "response_target": "customer"}

        revision_index = int(memory_state.get("plan_revision_index", 0))
        hardship_reason = str(memory_state.get("hardship_reason", "income_reduction"))
        case_id = str(memory_state.get("active_case_id", "COLL-1001"))

        if self._needs_discount_specialist(user_input) and case_id:
            return {
                "route": "continue",
                "response": "Routing internally to discount planning specialist.",
                "response_target": "discount_planning_agent",
                "handoff_payload": {
                    "case_id": case_id,
                    "reason_for_handoff": "Need optimized discount/EMI proposal for ongoing negotiation",
                    "current_plan": memory_state.get("current_plan"),
                    "hardship_reason": hardship_reason,
                    "target_monthly_emi": self._extract_amount(user_input),
                },
            }

        if mode != "hardship_negotiation":
            if plan_origin in {"pre_plan_intent", "post_memory_plan_intent"}:
                decision = SimpleNamespace(
                    thought="Generated direct proposal response without additional tool calls.",
                    tool_call=None,
                    respond_directly=True,
                    response_text=self._build_direct_plan_response(user_input=user_input, memory_state=memory_state),
                    done=True,
                )
                return {"route": "continue", "decision": decision}
            return {"route": "continue", "response_target": "customer"}

        if observed_tool == "plan_propose":
            if memory is not None and isinstance(output, dict):
                memory.set_state(current_plan=output, plan_revision_index=int(memory_state.get("plan_revision_index", 0)))
            return {"route": "continue", "response_target": "customer"}

        should_propose = False

        if observed_tool == "offer_eligibility":
            should_propose = True
        if observed_tool == "channel_switch" and not memory_state.get("current_plan"):
            should_propose = True
        if self._is_plan_rejection(user_input) and memory_state.get("current_plan"):
            should_propose = True
            revision_index += 1
        if self._is_plan_request(user_input) and case_id:
            should_propose = True

        if not should_propose:
            return {"route": "continue", "response_target": "customer"}

        max_installment = self._extract_amount(user_input)
        arguments: dict[str, Any] = {
            "case_id": case_id,
            "hardship_reason": hardship_reason,
            "revision_index": revision_index,
        }
        if max_installment is not None:
            arguments["max_installment_amount"] = max_installment

        if memory is not None:
            memory.set_state(plan_revision_index=revision_index)

        decision = SimpleNamespace(
            thought="Routing to plan proposal tool based on hardship negotiation state.",
            tool_call=SimpleNamespace(tool_name="plan_propose", arguments=arguments),
            respond_directly=False,
            response_text=None,
            done=False,
        )
        return {
            "route": "propose",
            "decision": decision,
        }

    def route(self, state: AgentState) -> str:
        return str(state.get("route", "continue"))

    @staticmethod
    def _is_plan_rejection(text: str) -> bool:
        lowered = text.lower()
        return any(key in lowered for key in ["not work", "can't", "cannot", "too high", "reject", "no,", "no "])

    @staticmethod
    def _is_plan_request(text: str) -> bool:
        lowered = text.lower()
        return any(key in lowered for key in ["payment plan", "plan option", "need plan", "proposal"])

    @staticmethod
    def _extract_amount(text: str) -> float | None:
        match = re.search(r"(?:\$|inr\s*)?(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if not match:
            return None
        return float(match.group(1))

    @staticmethod
    def _needs_discount_specialist(text: str) -> bool:
        lowered = text.lower()
        keywords = [
            "discount",
            "waiver",
            "concession",
            "benefit",
            "lower emi",
            "reduce emi",
            "settlement",
        ]
        return any(keyword in lowered for keyword in keywords)

    @staticmethod
    def _build_direct_plan_response(*, user_input: str, memory_state: dict[str, Any]) -> str:
        case_id = str(memory_state.get("active_case_id", "COLL-1001"))
        channel = str(memory_state.get("active_channel", "sms"))
        lowered = user_input.lower()
        if any(token in lowered for token in ["pay now", "payment link", "link"]):
            return (
                f"Proposed plan for {case_id}: complete identity verification, confirm current dues, "
                "generate a payment link, and close the case after payment confirmation."
            )
        if any(token in lowered for token in ["cannot pay", "hardship", "discount", "settlement", "waiver"]):
            return (
                f"Proposed plan for {case_id}: verify hardship reason, check policy eligibility for concessions, "
                "share the best eligible repayment option, and schedule follow-up on the same channel "
                f"({channel}) if immediate payment is not possible."
            )
        return (
            f"Proposed plan for {case_id}: verify customer identity, explain overdue dues and policy options, "
            "attempt payment collection, and if payment is deferred, capture a promise-to-pay and schedule follow-up."
        )

    @staticmethod
    def _build_discount_offer_response(output: dict[str, Any]) -> str:
        recommended = output.get("recommended_offer", {}) if isinstance(output, dict) else {}
        monthly_emi = recommended.get("monthly_emi")
        tenure = recommended.get("tenure_months")
        if monthly_emi is not None and tenure is not None:
            return (
                f"I can offer a revised plan at {float(monthly_emi):.2f} per month for {int(tenure)} months. "
                "If this works for you, I will capture your promise-to-pay and schedule follow-up."
            )
        return "I have prepared revised discount and EMI options. Please confirm if you want to proceed with the recommended offer."

    @staticmethod
    def _is_conversation_termination(text: str) -> bool:
        lowered = text.lower().strip()
        if not lowered:
            return False
        signals = [
            "bye",
            "goodbye",
            "thanks that's all",
            "thank you that's all",
            "close this",
            "done for now",
            "that's all",
            "end conversation",
            "you can close",
        ]
        return any(signal in lowered for signal in signals)
