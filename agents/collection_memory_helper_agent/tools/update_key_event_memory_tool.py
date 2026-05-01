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
        key_events = self._extract_key_events(messages)
        summary = self._summarize(messages)

        global_updates = 0
        for event in key_events:
            event_type = event.split(":", 1)[0].strip().lower().replace(" ", "_")
            self.repository.upsert_global_event(event_type=event_type, signal=event)
            global_updates += 1

        self.repository.upsert_user_memory(
            session_id=input.session_id,
            user_memory={
                "case_id": input.conversation_state.get("active_case_id"),
                "summary": summary,
                "key_events": key_events,
                "trigger": input.trigger,
                "next_considerations": self._next_considerations(key_events=key_events, state=input.conversation_state),
            },
        )

        return UpdateKeyEventMemoryOutput(
            status="updated",
            global_events_updated=global_updates,
            user_session_id=input.session_id,
            extracted_key_events=key_events,
            user_summary=summary,
        )

    @staticmethod
    def _extract_key_events(messages: list[dict[str, Any]]) -> list[str]:
        events: list[str] = []
        for row in messages[-30:]:
            role = str(row.get("role", "")).lower()
            content = str(row.get("content", "")).strip()
            lowered = content.lower()
            if not content:
                continue
            if role == "user":
                if "discount" in lowered or "waiver" in lowered or "lower emi" in lowered:
                    events.append(f"discount_interest: {content}")
                if "cannot pay" in lowered or "can't pay" in lowered or "hardship" in lowered:
                    events.append(f"hardship_signal: {content}")
                if "bye" in lowered or "goodbye" in lowered or "that's all" in lowered:
                    events.append(f"conversation_termination: {content}")
            if role == "agent":
                if "payment link" in lowered:
                    events.append(f"payment_link_offered: {content}")
                if "promise" in lowered:
                    events.append(f"promise_flow: {content}")
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
    def _next_considerations(*, key_events: list[str], state: dict[str, Any]) -> list[str]:
        hints: list[str] = []
        if any(event.startswith("discount_interest") for event in key_events):
            hints.append("Start next follow-up with discount and EMI options first.")
        if any(event.startswith("hardship_signal") for event in key_events):
            hints.append("Check hardship policy path before immediate payment push.")
        if state.get("current_plan"):
            hints.append("Reuse current_plan context before proposing a new plan.")
        if not hints:
            hints.append("Begin next turn with dues summary and one clear next action.")
        return hints
