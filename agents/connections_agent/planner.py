"""Rule-based planner for the Connections Agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from agents.connections_agent.tools import followup_decision_from_observation, observation_to_response


@dataclass(slots=True)
class ConnectionsRulePlanner:
    """Chooses tools and arguments without requiring an LLM backend."""

    def plan(
        self,
        *,
        user_input: str,
        memory: Any | None = None,
        observation: dict[str, Any] | None = None,
        memory_context: dict[str, Any] | None = None,
        available_tools: list[Any] | None = None,
    ) -> Any:
        del memory_context, available_tools
        text = user_input.strip()

        if observation:
            followup = followup_decision_from_observation(observation)
            if followup is not None:
                return followup
            return SimpleNamespace(
                thought="Responding with latest tool output summary.",
                tool_call=None,
                respond_directly=True,
                response_text=observation_to_response(observation),
                done=True,
            )

        args = self._extract_arguments(text)
        explicit_tool = self._extract_explicit_tool(text)
        if explicit_tool is not None:
            return self._tool_decision(explicit_tool, args)

        lowered = text.lower()
        if "prioritize" in lowered or "queue" in lowered:
            return self._tool_decision("case_prioritize", args)
        if "verify" in lowered or "kyc" in lowered:
            return self._tool_decision("customer_verify", args)
        if "policy" in lowered:
            return self._tool_decision("loan_policy_lookup", args)
        if "dues" in lowered or "emi" in lowered:
            return self._tool_decision("dues_explain_build", args)
        if "offer" in lowered or "discount" in lowered or "waiver" in lowered:
            return self._tool_decision("offer_eligibility", args)
        if "payment link" in lowered or "pay now" in lowered:
            return self._tool_decision("payment_link_create", args)
        if "payment status" in lowered:
            return self._tool_decision("payment_status_check", args)
        if "promise" in lowered:
            return self._tool_decision("promise_capture", args)
        if "follow" in lowered:
            return self._tool_decision("followup_schedule", args)
        if "escalate" in lowered:
            return self._tool_decision("human_escalation", args)
        if "disposition" in lowered or "close case" in lowered:
            return self._tool_decision("disposition_update", args)
        if "contact" in lowered or "call" in lowered:
            return self._tool_decision("contact_attempt", args)
        if "fetch" in lowered or "defaulter" in lowered or "case" in lowered:
            return self._tool_decision("case_fetch", args)

        summary = "Use '<tool_name> key=value ...' for deterministic offline runs. Example: case_fetch case_id=COLL-1001"
        if memory is not None:
            memory.set_state(last_planner_hint=summary)
        return SimpleNamespace(
            thought="No tool intent detected.",
            tool_call=None,
            respond_directly=True,
            response_text=summary,
            done=True,
        )

    @staticmethod
    def _extract_explicit_tool(text: str) -> str | None:
        candidate = text.strip().split(maxsplit=1)[0].strip().lower()
        known = {
            "case_fetch",
            "case_prioritize",
            "contact_attempt",
            "customer_verify",
            "loan_policy_lookup",
            "dues_explain_build",
            "offer_eligibility",
            "payment_link_create",
            "payment_status_check",
            "promise_capture",
            "followup_schedule",
            "disposition_update",
            "human_escalation",
        }
        if candidate in known:
            return candidate
        return None

    def _tool_decision(self, tool_name: str, args: dict[str, Any]) -> Any:
        normalized = self._normalize_for_tool(tool_name, args)
        return SimpleNamespace(
            thought=f"Executing {tool_name} with rule-based planner.",
            tool_call=SimpleNamespace(tool_name=tool_name, arguments=normalized),
            respond_directly=False,
            response_text=None,
            done=False,
        )

    @staticmethod
    def _extract_arguments(text: str) -> dict[str, Any]:
        pairs = re.findall(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([^\s,]+)", text)
        args: dict[str, Any] = {}
        for key, value in pairs:
            clean = value.strip().strip("'\"")
            lowered = clean.lower()
            if lowered in {"true", "false"}:
                args[key] = lowered == "true"
                continue
            if re.fullmatch(r"-?\d+", clean):
                args[key] = int(clean)
                continue
            if re.fullmatch(r"-?\d+\.\d+", clean):
                args[key] = float(clean)
                continue
            args[key] = clean

        if "case_id" not in args:
            match = re.search(r"(COLL-\d+|CASE-\d+)", text, re.IGNORECASE)
            if match:
                args["case_id"] = match.group(1).upper()
        if "customer_id" not in args:
            match = re.search(r"(CUST-\d+)", text, re.IGNORECASE)
            if match:
                args["customer_id"] = match.group(1).upper()
        if "loan_id" not in args:
            match = re.search(r"(LOAN-\d+)", text, re.IGNORECASE)
            if match:
                args["loan_id"] = match.group(1).upper()
        return args

    def _normalize_for_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(args)
        now = datetime.now(UTC)

        if tool_name == "case_fetch":
            normalized.setdefault("limit", 20)
        elif tool_name == "case_prioritize":
            normalized.setdefault("top_k", 10)
        elif tool_name == "contact_attempt":
            normalized.setdefault("channel", "voice")
            normalized.setdefault("reached", False)
        elif tool_name == "customer_verify":
            normalized.setdefault("challenge_answers", {})
        elif tool_name == "dues_explain_build":
            normalized.setdefault("locale", "en-IN")
        elif tool_name == "offer_eligibility":
            normalized.setdefault("hardship_flag", False)
        elif tool_name == "payment_link_create":
            normalized.setdefault("channel", "whatsapp")
            normalized.setdefault("amount", 5000.0)
            normalized.setdefault("expiry_minutes", 60)
        elif tool_name == "promise_capture":
            normalized.setdefault("promised_date", (now + timedelta(days=5)).date().isoformat())
            normalized.setdefault("promised_amount", 5000.0)
            normalized.setdefault("channel", "voice")
        elif tool_name == "followup_schedule":
            normalized.setdefault("scheduled_for", (now + timedelta(days=5)).date().isoformat())
            normalized.setdefault("preferred_channel", "voice")
            normalized.setdefault("reason", "promise_to_pay")
        elif tool_name == "disposition_update":
            normalized.setdefault("disposition_code", "pending_followup")
            normalized.setdefault("notes", "Disposition updated by offline planner")
        elif tool_name == "human_escalation":
            normalized.setdefault("reason", "manual_review_requested")

        return normalized
