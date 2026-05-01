from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.collection_memory_helper_agent.repository import CollectionMemoryRepository
from agents.collection_memory_helper_agent.tools.schemas import UpdateKeyEventMemoryInput, UpdateKeyEventMemoryOutput
from src.tools.base import BaseTool


@dataclass(slots=True)
class UpdateKeyEventMemoryTool(BaseTool[UpdateKeyEventMemoryInput, UpdateKeyEventMemoryOutput]):
    repository: CollectionMemoryRepository
    name: str = "update_key_event_memory"
    description: str = "Extract key events and update global/user memory JSON stores."
    input_schema = UpdateKeyEventMemoryInput
    output_schema = UpdateKeyEventMemoryOutput

    def execute(self, input: UpdateKeyEventMemoryInput) -> UpdateKeyEventMemoryOutput:
        messages = list(input.conversation_messages)
        user_id = self._resolve_user_id(input)
        key_points = self._extract_key_points(messages)
        summary = self._summarize(messages)
        outcome = self._classify_outcome(messages=messages, trigger=input.trigger, key_points=key_points)

        global_updates = 0
        for key_point in key_points:
            self.repository.upsert_global_cue(
                outcome="successful" if outcome == "successful" else "unsuccessful",
                cue=key_point,
                signal=summary,
                user_id=user_id,
            )
            global_updates += 1

        self.repository.upsert_user_memory(
            user_id=user_id,
            session_id=input.session_id,
            user_memory={
                "case_id": input.conversation_state.get("active_case_id"),
                "preferred_channel": input.conversation_state.get("active_channel", "sms"),
                "risk_band": input.conversation_state.get("risk_band", "unknown"),
                "summary": summary,
                "procedural_key_points": key_points,
                "trigger": input.trigger,
                "conversation_outcome": outcome,
                "follow_up_considerations": self._follow_up_considerations(
                    key_points=key_points,
                    state=input.conversation_state,
                    outcome=outcome,
                ),
            },
        )

        return UpdateKeyEventMemoryOutput(
            status="updated",
            user_id=user_id,
            global_cues_updated=global_updates,
            conversation_outcome=outcome,
            extracted_key_points=key_points,
            user_summary=summary,
        )

    @staticmethod
    def _resolve_user_id(input: UpdateKeyEventMemoryInput) -> str:
        if input.user_id and str(input.user_id).strip():
            return str(input.user_id).strip()
        state_user = input.conversation_state.get("active_user_id")
        if state_user is not None and str(state_user).strip():
            return str(state_user).strip()
        return f"SESSION::{input.session_id}"

    @staticmethod
    def _extract_key_points(messages: list[dict[str, Any]]) -> list[str]:
        events: list[str] = []
        for row in messages[-30:]:
            role = str(row.get("role", "")).lower()
            content = str(row.get("content", "")).strip()
            lowered = content.lower()
            if not content:
                continue
            if role == "user":
                if "discount" in lowered or "waiver" in lowered or "lower emi" in lowered:
                    events.append("User asked for discount/waiver style assistance.")
                if "cannot pay" in lowered or "can't pay" in lowered or "hardship" in lowered:
                    events.append("User reported hardship or inability to pay immediately.")
                if "pay now" in lowered or "payment link" in lowered:
                    events.append("User signaled near-term payment intent.")
            if role == "agent":
                if "payment link" in lowered:
                    events.append("Agent offered payment link after dues discussion.")
                if "promise" in lowered:
                    events.append("Agent moved conversation toward promise-to-pay capture.")
                if "verify" in lowered:
                    events.append("Agent emphasized identity verification step before account actions.")
        deduped: list[str] = []
        for event in events:
            if event not in deduped:
                deduped.append(event)
        return deduped[-20:]

    @staticmethod
    def _summarize(messages: list[dict[str, Any]]) -> str:
        if not messages:
            return "No conversation content available for summarization."
        latest = messages[-12:]
        rendered = []
        for row in latest:
            role = str(row.get("role", "user")).lower()
            content = str(row.get("content", "")).strip()
            if not content:
                continue
            rendered.append(f"{role}: {content}")
        if not rendered:
            return "No usable conversational utterances found."
        return " | ".join(rendered)[:1600]

    @staticmethod
    def _classify_outcome(*, messages: list[dict[str, Any]], trigger: dict[str, Any], key_points: list[str]) -> str:
        trigger_reason = str(trigger.get("reason", "")).lower()
        text = " ".join(str(item.get("content", "")).lower() for item in messages[-20:])
        if "payment intent" in " ".join(key_points).lower():
            return "successful"
        if "conversation_termination" in trigger_reason and ("promise" in text or "will pay" in text):
            return "successful"
        if any(token in text for token in ["cannot pay", "can't pay", "hardship", "dispute", "wrong number"]):
            return "unsuccessful"
        return "neutral"

    @staticmethod
    def _follow_up_considerations(*, key_points: list[str], state: dict[str, Any], outcome: str) -> list[str]:
        hints: list[str] = []
        if any("discount" in event.lower() or "waiver" in event.lower() for event in key_points):
            hints.append("Start next follow-up with discount and EMI options first.")
        if any("hardship" in event.lower() for event in key_points):
            hints.append("Check hardship policy path before immediate payment push.")
        if state.get("current_plan"):
            hints.append("Reuse current_plan context before proposing a new plan.")
        if outcome == "successful":
            hints.append("Confirm payment status first, then close with disposition update.")
        if outcome == "unsuccessful":
            hints.append("Begin with empathy and one actionable option instead of broad choices.")
        if not hints:
            hints.append("Begin next turn with dues summary and one clear next action.")
        return hints
