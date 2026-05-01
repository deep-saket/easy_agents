"""Collection-specific response node with target routing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.nodes.response_node import ResponseNode
from src.nodes.types import AgentState, NodeUpdate


@dataclass(slots=True)
class CollectionResponseNode(ResponseNode):
    """Emits response text and a response target for next-hop routing."""

    default_target: str = "customer"

    def execute(self, state: AgentState) -> NodeUpdate:
        plan = state.get("plan_proposal") if isinstance(state.get("plan_proposal"), dict) else {}
        if plan:
            update: NodeUpdate = {"response": self._render_from_proposal(state=state, proposal=plan)}
            plan_target = str(plan.get("target", "")).strip().lower()
            if plan_target:
                update["response_target"] = plan_target
        else:
            update = ResponseNode.execute(self, state)

        target = str(update.get("response_target", state.get("response_target", self.default_target))).strip().lower()
        if target not in {"customer", "self", "discount_planning_agent"}:
            target = self.default_target
        update["response_target"] = target
        return update

    def route(self, state: AgentState) -> str:
        target = str(state.get("response_target", self.default_target)).strip().lower()
        if target not in {"customer", "self", "discount_planning_agent"}:
            return self.default_target
        return target

    def _render_from_proposal(self, *, state: AgentState, proposal: dict[str, Any]) -> str:
        if self.llm is not None:
            llm_response = self._llm_render_from_proposal(state=state, proposal=proposal)
            if llm_response:
                return llm_response
        return self._fallback_render_from_proposal(proposal=proposal)

    def _llm_render_from_proposal(self, *, state: AgentState, proposal: dict[str, Any]) -> str | None:
        user_input = str(state.get("user_input", ""))
        observation = state.get("observation")
        memory = state.get("memory")
        memory_state = dict(getattr(memory, "state", {})) if memory is not None else {}
        customer_name = str(memory_state.get("active_customer_name", "Customer"))
        case_id = str(memory_state.get("active_case_id", "COLL-1001"))

        system_prompt = (
            f"{self.system_prompt or ''}\n"
            "You are a bank collections assistant. Convert plan_proposal into a customer-facing response.\n"
            "Never mention internal terms such as plan_proposal, plan, node, tool, or workflow.\n"
            "Use clear, polite, concise language and ask one concrete next-step question when needed."
        ).strip()
        user_prompt = (
            f"User input: {user_input}\n"
            f"Customer name: {customer_name}\n"
            f"Case id: {case_id}\n"
            f"Plan proposal: {json.dumps(proposal, ensure_ascii=True)}\n"
            f"Observation: {json.dumps(observation, ensure_ascii=True, default=str)}\n"
            "Generate only the final customer-facing response text."
        )
        try:
            response = self.llm.generate(system_prompt, user_prompt).strip()
        except Exception:
            return None
        return response or None

    def _fallback_render_from_proposal(self, *, proposal: dict[str, Any]) -> str:
        intent = str(proposal.get("intent", "")).strip().lower()
        if intent == "outbound_opening":
            ctx = proposal.get("opening_context") if isinstance(proposal.get("opening_context"), dict) else {}
            name = str(ctx.get("customer_name", "Customer")).strip() or "Customer"
            case_id = str(ctx.get("case_id", "COLL-1001"))
            overdue = float(ctx.get("overdue_amount", 0.0))
            prior_signal = str(ctx.get("prior_signal", "")).strip()
            extra = f" {prior_signal}" if prior_signal else ""
            return (
                f"Hello {name}, this is the collections team calling regarding case {case_id}. "
                f"Our records show an overdue amount of INR {overdue:.2f}. "
                "I can help you clear dues now or discuss a suitable repayment arrangement."
                f"{extra} Are you available to proceed with payment today?"
            )

        if intent == "help_options":
            ctx = proposal.get("help_context") if isinstance(proposal.get("help_context"), dict) else {}
            name = str(ctx.get("customer_name", "Customer")).strip() or "Customer"
            case_id = str(ctx.get("case_id", "COLL-1001"))
            return (
                f"Sure {name}, I can help you in three ways for case {case_id}: "
                "1) pay dues now, 2) set a repayment arrangement if full payment is difficult, "
                "or 3) schedule a follow-up date. "
                "If you want, I can first verify your identity and then share exact due details."
            )

        if intent == "conversation_termination":
            return "Thank you. I am closing this conversation now."

        if intent == "loop_guard":
            return (
                "Please confirm one concrete next step: pay now, request a revised arrangement, or schedule follow-up."
            )

        if intent == "discount_recommendation":
            rec = (
                proposal.get("discount_recommendation", {}).get("recommended_offer", {})
                if isinstance(proposal.get("discount_recommendation"), dict)
                else {}
            )
            monthly = rec.get("monthly_emi")
            tenure = rec.get("tenure_months")
            if monthly is not None and tenure is not None:
                return (
                    f"I can offer a revised plan at INR {float(monthly):.2f} per month for {int(tenure)} months. "
                    "If this works for you, I will capture your promise-to-pay and schedule follow-up."
                )
            return "I have prepared revised discount and EMI options. Please confirm if you want to proceed."

        if intent == "case_not_found":
            return "I could not find an active dues case right now. Please confirm your case ID or customer ID."

        if intent == "case_snapshot":
            snap = proposal.get("case_snapshot") if isinstance(proposal.get("case_snapshot"), dict) else {}
            customer_name = str(snap.get("customer_name", "Customer")).strip() or "Customer"
            case_id = str(snap.get("case_id", "COLL-1001"))
            overdue = float(snap.get("overdue_amount", 0.0))
            emi = float(snap.get("emi_amount", 0.0))
            late = float(snap.get("late_fee", 0.0))
            dpd = int(snap.get("dpd", 0))
            return (
                f"Hello {customer_name}, this is the collections desk regarding case {case_id}. "
                f"Overdue amount is INR {overdue:.2f}, EMI is INR {emi:.2f}, late fee is INR {late:.2f}, "
                f"and the account is {dpd} days past due. "
                "Would you like to pay now, request a repayment arrangement, or schedule a follow-up?"
            )

        if intent == "plan_offer":
            offer = proposal.get("plan_offer") if isinstance(proposal.get("plan_offer"), dict) else {}
            months = offer.get("months")
            monthly = offer.get("monthly_amount")
            first_due = offer.get("first_due_date")
            if months is not None and monthly is not None:
                return (
                    f"I can offer a {int(months)}-month plan at INR {float(monthly):.2f} per month. "
                    f"First due date is {first_due}. Does this work for you?"
                )
            return "I can share a repayment plan option now. Would you like me to proceed?"

        draft = str(proposal.get("draft_response", "")).strip()
        if draft:
            return draft

        plan_outline = str(proposal.get("plan_outline", "")).strip()
        if plan_outline:
            return self._render_plan_outline(plan_outline)

        return "Please confirm how you would like to proceed with your dues."

    @staticmethod
    def _render_plan_outline(plan_outline: str) -> str:
        text = plan_outline.strip()
        if not text:
            return "Please confirm how you would like to proceed with your dues."

        normalized = re.sub(r"^Proposed plan for\s+[^:]+:\s*", "", text, flags=re.IGNORECASE).strip()
        executed_match = re.match(r"^Executed\s+([a-zA-Z0-9_]+)\s*:\s*(.*)$", text)
        if executed_match:
            details = executed_match.group(2).strip()
            if details:
                return (
                    f"I checked this for you: {details}. "
                    "Please tell me whether you want to pay now, request a revised arrangement, or schedule follow-up."
                )
            return "I completed the required verification step. Please tell me your preferred next action."

        if not normalized:
            normalized = text

        # Convert planning language into delivery language for end-user/agent handoff.
        normalized = normalized[0].upper() + normalized[1:] if len(normalized) > 1 else normalized.upper()
        if normalized.endswith("."):
            normalized = normalized[:-1]
        return (
            f"Here is the next best way to proceed: {normalized}. "
            "If you agree, I will execute this now."
        )
