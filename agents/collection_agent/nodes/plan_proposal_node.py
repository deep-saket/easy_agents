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
        existing_plan = self._get_existing_conversation_plan(state=state, memory_state=memory_state)

        def with_plan(update: NodeUpdate) -> NodeUpdate:
            response_target = str(update.get("response_target", "customer")).strip().lower() or "customer"
            route = str(update.get("route", "continue")).strip().lower() or "continue"
            proposal = update.get("plan_proposal") if isinstance(update.get("plan_proposal"), dict) else {}
            plan = self._build_or_update_conversation_plan(
                existing_plan=existing_plan,
                user_input=user_input,
                memory_state=memory_state,
                mode=mode,
                plan_origin=plan_origin,
                response_target=response_target,
                route=route,
                observed_tool=observed_tool,
                proposal=proposal,
            )
            update["conversation_plan"] = plan
            if proposal:
                proposal["conversation_plan_id"] = plan.get("plan_id")
                proposal["conversation_plan_version"] = plan.get("version")
                proposal["conversation_plan_current_node"] = plan.get("current_node_id")
                proposal["conversation_plan"] = plan
                update["plan_proposal"] = proposal
            if memory is not None:
                memory.set_state(active_conversation_plan=plan)
            return update

        if bool(memory_state.get("agent_loop_blocked", False)):
            if memory is not None:
                memory.set_state(agent_loop_blocked=False)
            return with_plan({
                "route": "continue",
                "response_target": "customer",
                "plan_proposal": {
                    "target": "customer",
                    "intent": "loop_guard",
                    "guidance": "Internal planning loop exceeded threshold.",
                    "next_actions": ["pay_now", "plan_revision", "schedule_followup"],
                    "plan_origin": "loop_guard",
                },
            })

        if self._is_conversation_termination(user_input):
            return with_plan({
                "route": "continue",
                "response_target": "customer",
                "plan_proposal": {
                    "target": "customer",
                    "intent": "conversation_termination",
                    "guidance": "Conversation is being closed politely.",
                    "plan_origin": "conversation_termination",
                },
                "additional_targets": ["collection_memory_helper_agent"],
                "memory_helper_trigger": {
                    "reason": "conversation_termination",
                    "final_user_message": user_input,
                },
            })

        discount_recommendation = memory_state.get("discount_recommendation")
        if isinstance(discount_recommendation, dict) and discount_recommendation:
            if memory is not None:
                memory.set_state(discount_recommendation=None)
            return with_plan({
                "route": "continue",
                "response_target": "customer",
                "plan_proposal": {
                    "target": "customer",
                    "intent": "discount_recommendation",
                    "discount_recommendation": discount_recommendation,
                    "plan_origin": "discount_recommendation",
                },
            })

        revision_index = int(memory_state.get("plan_revision_index", 0))
        hardship_reason = str(memory_state.get("hardship_reason", "income_reduction"))
        case_id = str(memory_state.get("active_case_id", "COLL-1001"))

        if self._needs_discount_specialist(user_input) and case_id:
            return with_plan({
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
            })

        if mode != "hardship_negotiation":
            plan_proposal = self._build_plan_proposal(
                user_input=user_input,
                memory_state=memory_state,
                observation=(observation if isinstance(observation, dict) else None),
                decision=decision,
                default_plan=self._build_generic_plan_outline(user_input=user_input, memory_state=memory_state),
                plan_origin=plan_origin,
                mode=mode,
            )
            return with_plan({
                "route": "continue",
                "response_target": str(plan_proposal.get("target", "customer")),
                "plan_proposal": plan_proposal,
            })

        if observed_tool == "plan_propose":
            if memory is not None and isinstance(output, dict):
                memory.set_state(current_plan=output, plan_revision_index=int(memory_state.get("plan_revision_index", 0)))
            plan_proposal = self._build_plan_proposal(
                user_input=user_input,
                memory_state=memory_state,
                observation=(observation if isinstance(observation, dict) else None),
                decision=decision,
                default_plan=self._build_generic_plan_outline(user_input=user_input, memory_state=memory_state),
                plan_origin=plan_origin,
                mode=mode,
            )
            return with_plan({
                "route": "continue",
                "response_target": "customer",
                "plan_proposal": plan_proposal,
            })

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
                default_plan=self._build_generic_plan_outline(user_input=user_input, memory_state=memory_state),
                plan_origin=plan_origin,
                mode=mode,
            )
            return with_plan({
                "route": "continue",
                "response_target": str(plan_proposal.get("target", "customer")),
                "plan_proposal": plan_proposal,
            })

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
        return with_plan({
            "route": "propose",
            "decision": decision,
            "response_target": "self",
        })

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
    def _build_generic_plan_outline(*, user_input: str, memory_state: dict[str, Any]) -> str:
        case_id = str(memory_state.get("active_case_id", "COLL-1001"))
        lowered = user_input.lower()
        if any(token in lowered for token in ["pay now", "payment link", "link", "proceed with payment"]):
            return (
                f"Plan for {case_id}: confirm customer identity and dues context, complete immediate payment flow, "
                "and confirm closure after payment acknowledgment."
            )
        if any(token in lowered for token in ["cannot pay", "hardship", "discount", "settlement", "waiver", "emi"]):
            return (
                f"Plan for {case_id}: validate hardship constraints, determine eligible assistance options, "
                "propose revised repayment path, and capture next commitment with follow-up."
            )
        return (
            f"Plan for {case_id}: verify account context, provide concise dues explanation, "
            "collect payment intent, and capture commitment or follow-up details."
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
        mode: str,
    ) -> dict[str, Any]:
        decision_text = str(getattr(decision, "response_text", "") or "").strip()
        decision_target = str(getattr(decision, "response_target", "") or "").strip().lower()
        target = decision_target if decision_target in {"customer", "self", "discount_planning_agent"} else "customer"
        observed_tool = str(observation.get("tool_name", "")) if isinstance(observation, dict) else ""
        output = observation.get("output", {}) if isinstance(observation, dict) else {}

        plan_outline = default_plan
        if decision_text:
            if decision_text.lower().startswith("proposed plan for ") or decision_text.lower().startswith("plan for "):
                plan_outline = decision_text
            elif decision_text.startswith("Executed "):
                plan_outline = f"Tool execution result observed: {decision_text}"
            else:
                plan_outline = f"Direct response path selected: {decision_text}"
        elif observed_tool:
            plan_outline = (
                f"Observation-driven plan: interpret `{observed_tool}` output, provide the next customer response, "
                "and request one concrete next action."
            )

        return {
            "target": target,
            "intent": "generic_plan",
            "plan_outline": plan_outline,
            "draft_response": decision_text if decision_text and not decision_text.startswith("Executed ") else "",
            "plan_origin": plan_origin or "default_direct_plan",
            "mode": mode,
            "context": {
                "case_id": str(memory_state.get("active_case_id", "COLL-1001")),
                "customer_name": str(memory_state.get("active_customer_name", "Customer")).strip() or "Customer",
                "overdue_amount": float(memory_state.get("active_overdue_amount", 0.0) or 0.0),
                "observed_tool": observed_tool,
                "observed_tool_output": output if isinstance(output, dict) else {},
            },
            "next_actions": self._derive_next_actions(user_input=user_input, mode=mode, observed_tool=observed_tool),
        }

    @staticmethod
    def _derive_next_actions(*, user_input: str, mode: str, observed_tool: str) -> list[str]:
        lowered = user_input.lower()
        actions: list[str] = ["confirm_identity", "confirm_dues", "collect_payment_intent"]
        if "pay now" in lowered or "payment link" in lowered:
            actions.append("complete_payment_flow")
        if mode == "hardship_negotiation":
            actions.append("evaluate_assistance_options")
        if observed_tool:
            actions.append("interpret_tool_observation")
        actions.append("capture_next_commitment")
        return actions

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

    @staticmethod
    def _get_existing_conversation_plan(*, state: AgentState, memory_state: dict[str, Any]) -> dict[str, Any]:
        state_plan = state.get("conversation_plan")
        if isinstance(state_plan, dict) and state_plan:
            return dict(state_plan)
        memory_plan = memory_state.get("active_conversation_plan")
        if isinstance(memory_plan, dict) and memory_plan:
            return dict(memory_plan)
        return {}

    def _build_or_update_conversation_plan(
        self,
        *,
        existing_plan: dict[str, Any],
        user_input: str,
        memory_state: dict[str, Any],
        mode: str,
        plan_origin: str,
        response_target: str,
        route: str,
        observed_tool: str,
        proposal: dict[str, Any],
    ) -> dict[str, Any]:
        plan = self._create_initial_plan_graph(memory_state=memory_state, mode=mode) if not existing_plan else dict(existing_plan)
        plan.setdefault("nodes", [])
        plan.setdefault("edges", [])
        plan.setdefault("revision_log", [])
        plan.setdefault("status", "active")
        plan.setdefault("version", 1)
        plan.setdefault("objective", "Drive compliant collections conversation toward payment resolution.")
        plan.setdefault("plan_id", f"plan-{str(memory_state.get('active_case_id', 'COLL-1001')).strip().upper()}")

        previous_current = str(plan.get("current_node_id", ""))
        next_current = self._infer_current_node_id(
            user_input=user_input,
            observed_tool=observed_tool,
            response_target=response_target,
            route=route,
            proposal=proposal,
        )
        node_ids = {str(node.get("id")) for node in plan.get("nodes", []) if isinstance(node, dict)}
        if next_current not in node_ids:
            next_current = "collect_payment_intent"

        if previous_current and previous_current != next_current:
            for node in plan["nodes"]:
                if isinstance(node, dict) and str(node.get("id")) == previous_current and node.get("status") == "in_progress":
                    node["status"] = "done"

        for node in plan["nodes"]:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id", ""))
            if node_id == next_current:
                if route == "propose":
                    node["status"] = "in_progress"
                    node["owner"] = "collection_agent"
                elif response_target == "discount_planning_agent":
                    node["status"] = "blocked"
                    node["owner"] = "discount_planning_agent"
                elif response_target == "self":
                    node["status"] = "in_progress"
                    node["owner"] = "collection_agent"
                else:
                    node["status"] = "in_progress"
            elif node.get("status") not in {"done", "skipped"} and node.get("status") is None:
                node["status"] = "pending"

        lowered = user_input.lower()
        should_revise = (
            self._is_plan_rejection(user_input)
            or self._needs_discount_specialist(user_input)
            or "hardship" in lowered
            or "cannot pay" in lowered
            or response_target != "customer"
        )
        if should_revise:
            plan["version"] = int(plan.get("version", 1)) + 1
            plan["revision_log"].append(
                {
                    "revision": int(plan.get("version", 1)),
                    "reason": f"context shift: target={response_target}, route={route}, origin={plan_origin}",
                }
            )

        plan["current_node_id"] = next_current
        plan["previous_node_id"] = previous_current or None
        plan["next_node_ids"] = self._next_nodes_from_edges(nodes=plan.get("edges", []), current_node_id=next_current)
        plan["updated_from"] = plan_origin or "react"
        plan["last_response_target"] = response_target
        plan["status"] = "completed" if self._is_conversation_termination(user_input) else "active"
        return plan

    @staticmethod
    def _create_initial_plan_graph(*, memory_state: dict[str, Any], mode: str) -> dict[str, Any]:
        case_id = str(memory_state.get("active_case_id", "COLL-1001")).strip().upper() or "COLL-1001"
        return {
            "plan_id": f"plan-{case_id}",
            "version": 1,
            "status": "active",
            "mode": mode,
            "objective": "Move borrower conversation to payment, promise-to-pay, or compliant follow-up.",
            "current_node_id": "open_and_context",
            "previous_node_id": None,
            "next_node_ids": ["verify_identity"],
            "nodes": [
                {"id": "open_and_context", "label": "Open call and establish case context", "owner": "collection_agent", "status": "in_progress"},
                {"id": "verify_identity", "label": "Verify customer identity", "owner": "customer", "status": "pending"},
                {"id": "explain_dues", "label": "Explain dues and policy options", "owner": "customer", "status": "pending"},
                {"id": "collect_payment_intent", "label": "Collect payment intent", "owner": "customer", "status": "pending"},
                {"id": "evaluate_assistance", "label": "Evaluate discount/restructure assistance", "owner": "discount_planning_agent", "status": "pending"},
                {"id": "resolve_outcome", "label": "Finalize payment, promise, or follow-up", "owner": "customer", "status": "pending"},
            ],
            "edges": [
                {"from": "open_and_context", "to": "verify_identity", "condition": "case_context_ready"},
                {"from": "verify_identity", "to": "explain_dues", "condition": "identity_verified"},
                {"from": "explain_dues", "to": "collect_payment_intent", "condition": "dues_explained"},
                {"from": "collect_payment_intent", "to": "resolve_outcome", "condition": "pay_now"},
                {"from": "collect_payment_intent", "to": "evaluate_assistance", "condition": "cannot_pay_full"},
                {"from": "evaluate_assistance", "to": "resolve_outcome", "condition": "assistance_ready"},
            ],
            "revision_log": [],
            "updated_from": "initial",
            "last_response_target": "customer",
        }

    def _infer_current_node_id(
        self,
        *,
        user_input: str,
        observed_tool: str,
        response_target: str,
        route: str,
        proposal: dict[str, Any],
    ) -> str:
        lowered = user_input.lower()
        proposal_intent = str(proposal.get("intent", "")).strip().lower() if isinstance(proposal, dict) else ""
        if proposal_intent == "conversation_termination" or self._is_conversation_termination(user_input):
            return "resolve_outcome"
        if response_target == "discount_planning_agent":
            return "evaluate_assistance"
        if route == "propose":
            return "evaluate_assistance"
        if observed_tool in {"customer_verify"} or "verify" in lowered:
            return "verify_identity"
        if observed_tool in {"dues_explain_build", "loan_policy_lookup"} or any(
            token in lowered for token in ["dues", "overdue", "emi", "policy", "amount due"]
        ):
            return "explain_dues"
        if observed_tool in {"payment_link_create", "pay_by_phone_collect", "payment_status_check"} or any(
            token in lowered for token in ["pay now", "payment", "link", "settle"]
        ):
            return "resolve_outcome"
        if any(token in lowered for token in ["cannot pay", "hardship", "discount", "waiver", "restructure", "settlement"]):
            return "evaluate_assistance"
        return "collect_payment_intent"

    @staticmethod
    def _next_nodes_from_edges(*, nodes: list[Any], current_node_id: str) -> list[str]:
        next_nodes: list[str] = []
        for edge in nodes:
            if not isinstance(edge, dict):
                continue
            if str(edge.get("from", "")) != current_node_id:
                continue
            to = str(edge.get("to", "")).strip()
            if to:
                next_nodes.append(to)
        return next_nodes
