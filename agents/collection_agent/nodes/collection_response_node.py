"""Collection-specific response node with target routing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.nodes.response_node import ResponseNode
from src.nodes.types import AgentState, NodeUpdate


@dataclass(slots=True)
class CollectionResponseNode(ResponseNode):
    """Emits response text and a response target for next-hop routing."""

    default_target: str = "customer"

    def execute(self, state: AgentState) -> NodeUpdate:
        plan = state.get("plan_proposal") if isinstance(state.get("plan_proposal"), dict) else {}
        if plan:
            plan_message = str(plan.get("customer_message", "")).strip()
            if plan_message:
                update: NodeUpdate = {"response": plan_message}
            else:
                plan_outline = str(plan.get("plan_outline", "")).strip()
                if plan_outline:
                    update = {"response": self._render_plan_outline(plan_outline)}
                else:
                    update = ResponseNode.execute(self, state)
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
