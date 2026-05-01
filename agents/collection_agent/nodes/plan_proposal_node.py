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
        decision = state.get("decision")

        if bool(memory_state.get("agent_loop_blocked", False)):
            if memory is not None:
                memory.set_state(agent_loop_blocked=False)
            return {
                "route": "continue",
                "response_target": "customer",
                "plan_proposal": {
                    "target": "customer",
                    "customer_message": (
                        "I have been running internal planning loops for too long on this request. "
                        "Please confirm one concrete next step (pay now, ask for plan revision, or schedule follow-up)."
                    ),
                    "plan_origin": "loop_guard",
                },
            }

        if self._is_conversation_termination(user_input):
            return {
                "route": "continue",
                "response_target": "customer",
                "plan_proposal": {
                    "target": "customer",
                    "customer_message": "Thank you. I am closing this conversation now.",
                    "plan_origin": "conversation_termination",
                },
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
            return {
                "route": "continue",
                "response_target": "customer",
                "plan_proposal": {
                    "target": "customer",
                    "customer_message": response_text,
                    "plan_origin": "discount_recommendation",
                },
            }

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
            plan_proposal = self._build_plan_proposal(
                user_input=user_input,
                memory_state=memory_state,
                observation=(observation if isinstance(observation, dict) else None),
                decision=decision,
                default_plan=self._build_direct_plan_response(user_input=user_input, memory_state=memory_state),
                plan_origin=plan_origin,
            )
            return {
                "route": "continue",
                "response_target": str(plan_proposal.get("target", "customer")),
                "plan_proposal": plan_proposal,
            }

        if observed_tool == "plan_propose":
            if memory is not None and isinstance(output, dict):
                memory.set_state(current_plan=output, plan_revision_index=int(memory_state.get("plan_revision_index", 0)))
            plan_proposal = self._build_plan_proposal(
                user_input=user_input,
                memory_state=memory_state,
                observation=(observation if isinstance(observation, dict) else None),
                decision=decision,
                default_plan=self._build_direct_plan_response(user_input=user_input, memory_state=memory_state),
                plan_origin=plan_origin,
            )
            return {
                "route": "continue",
                "response_target": "customer",
                "plan_proposal": plan_proposal,
            }

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
            plan_proposal = self._build_plan_proposal(
                user_input=user_input,
                memory_state=memory_state,
                observation=(observation if isinstance(observation, dict) else None),
                decision=decision,
                default_plan=self._build_direct_plan_response(user_input=user_input, memory_state=memory_state),
                plan_origin=plan_origin,
            )
            return {
                "route": "continue",
                "response_target": str(plan_proposal.get("target", "customer")),
                "plan_proposal": plan_proposal,
            }

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

    def _build_plan_proposal(
        self,
        *,
        user_input: str,
        memory_state: dict[str, Any],
        observation: dict[str, Any] | None,
        decision: Any | None,
        default_plan: str,
        plan_origin: str,
    ) -> dict[str, Any]:
        opener_message = self._build_outbound_opening_message(
            user_input=user_input,
            memory_state=memory_state,
            plan_origin=plan_origin,
        )
        if opener_message:
            return {
                "target": "customer",
                "customer_message": opener_message,
                "plan_origin": "outbound_opening",
            }

        decision_text = str(getattr(decision, "response_text", "") or "").strip()
        decision_target = str(getattr(decision, "response_target", "") or "").strip().lower()
        target = decision_target if decision_target in {"customer", "self", "discount_planning_agent"} else "customer"

        # Prefer explicit direct-response text unless it is raw tool debug output.
        if decision_text and not decision_text.startswith("Executed "):
            if decision_text.lower().startswith("proposed plan for "):
                return {
                    "target": target,
                    "plan_outline": decision_text,
                    "plan_origin": "react_direct_plan_outline",
                }
            return {
                "target": target,
                "customer_message": decision_text,
                "plan_origin": "react_direct",
            }

        observed_tool = str(observation.get("tool_name", "")) if isinstance(observation, dict) else ""
        output = observation.get("output", {}) if isinstance(observation, dict) else {}

        if observed_tool == "case_fetch":
            total = int(output.get("total", 0)) if output.get("total") is not None else 0
            cases = output.get("cases") if isinstance(output.get("cases"), list) else []
            if total <= 0 or not cases:
                return {
                    "target": "customer",
                    "customer_message": (
                        "I could not find an active dues case right now. Please confirm your case ID or customer ID so I can proceed."
                    ),
                    "plan_origin": "tool_case_fetch",
                }
            primary = cases[0] if isinstance(cases[0], dict) else {}
            customer_name = str(memory_state.get("active_customer_name", "Customer")).strip() or "Customer"
            case_id = str(primary.get("case_id", memory_state.get("active_case_id", "COLL-1001")))
            overdue_amount = float(primary.get("overdue_amount", 0.0))
            emi_amount = float(primary.get("emi_amount", 0.0))
            dpd = int(primary.get("dpd", 0))
            late_fee = float(primary.get("late_fee", 0.0))
            return {
                "target": "customer",
                "customer_message": (
                    f"Hello {customer_name}, this is the collections desk regarding case {case_id}. "
                    f"Our records show overdue amount {overdue_amount:.2f}, EMI {emi_amount:.2f}, "
                    f"late fee {late_fee:.2f}, and {dpd} days past due. "
                    "Would you like to pay now, request a payment arrangement, or schedule a follow-up?"
                ),
                "plan_origin": "tool_case_fetch",
            }

        if observed_tool == "plan_propose" and isinstance(output, dict):
            months = output.get("months")
            monthly_amount = output.get("monthly_amount")
            first_due_date = output.get("first_due_date")
            if months is not None and monthly_amount is not None:
                return {
                    "target": "customer",
                    "customer_message": (
                        f"I can offer a {int(months)}-month plan at {float(monthly_amount):.2f} per month. "
                        f"First due date is {first_due_date}. Does this work for you?"
                    ),
                    "plan_origin": "tool_plan_propose",
                }

        if decision_text:
            if decision_text.lower().startswith("proposed plan for "):
                return {
                    "target": target,
                    "plan_outline": decision_text,
                    "plan_origin": "react_direct_raw_plan_outline",
                }
            if decision_text.startswith("Executed "):
                return {
                    "target": target,
                    "plan_outline": decision_text,
                    "plan_origin": "react_tool_summary",
                }
            return {
                "target": target,
                "customer_message": decision_text,
                "plan_origin": "react_direct_raw",
            }

        return {
            "target": "customer",
            "plan_outline": default_plan,
            "plan_origin": "default_direct_plan",
        }

    def _build_outbound_opening_message(
        self,
        *,
        user_input: str,
        memory_state: dict[str, Any],
        plan_origin: str,
    ) -> str | None:
        lowered = user_input.lower()
        if plan_origin != "pre_plan_intent" and "outbound collections call" not in lowered:
            return None
        if "first call pitch" not in lowered and "outbound collections call" not in lowered:
            return None

        customer_name = str(memory_state.get("active_customer_name", "Customer")).strip() or "Customer"
        case_id = str(memory_state.get("active_case_id", "COLL-1001")).strip() or "COLL-1001"
        overdue_amount = self._extract_named_amount(user_input=user_input, key="overdue_amount")
        if overdue_amount is None:
            overdue_amount = self._extract_amount(user_input) or 0.0

        user_memory = memory_state.get("user_key_event_memory")
        prior_signal = ""
        if isinstance(user_memory, dict):
            key_points = user_memory.get("key_points")
            if isinstance(key_points, list) and key_points:
                first_point = str(key_points[0]).strip()
                if first_point:
                    prior_signal = f" I also note from prior interactions: {first_point}."

        return (
            f"Hello {customer_name}, this is the collections team calling regarding case {case_id}. "
            f"Our records show an overdue amount of INR {float(overdue_amount):.2f}. "
            "I can help you clear dues now or discuss a suitable repayment arrangement."
            f"{prior_signal} Are you available to proceed with payment today?"
        )

    @staticmethod
    def _extract_named_amount(*, user_input: str, key: str) -> float | None:
        pattern = rf"{re.escape(key)}\s*=\s*(\d+(?:\.\d+)?)"
        match = re.search(pattern, user_input, re.IGNORECASE)
        if not match:
            return None
        return float(match.group(1))

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
