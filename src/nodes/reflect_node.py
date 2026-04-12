"""Created: 2026-03-31

Purpose: Implements the reusable reflection node for shared agent graphs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.memory.base import BaseMemoryStore
from src.memory.types import ReflectionMemory, ReflectionMemoryContent
from src.nodes.base import BaseGraphNode
from src.nodes.types import AgentState, NodeUpdate


@dataclass(slots=True)
class ReflectNode(BaseGraphNode):
    """Reflects on the current turn and optionally feeds critique back into the graph.

    The default contract always emits structured reflection state:

    - `reflection_feedback`
    - `reflection_complete`

    Additional behaviors remain configurable:

    - optional merged reflection feedback in `observation`
    - optional `memory_updates` for a later `MemoryNode`
    - optional durable reflection logging through `memory_store`
    """

    memory_store: BaseMemoryStore | None = None
    agent_name: str = "platform"
    llm: Any | None = None
    system_prompt: str | None = None
    user_prompt: str | None = None
    complete_route: str = "complete"
    incomplete_route: str = "incomplete"
    merge_feedback_into_observation: bool = False
    emit_memory_update: bool = False
    default_reason: str = "Reflection completed."
    default_is_complete: bool = True

    def execute(self, state: AgentState) -> NodeUpdate:
        """Runs reflection for the current graph state."""
        self._record_llm_usage(state, node_name="reflect")
        observation = state.get("observation")
        decision = state.get("decision")
        self._store_reflection_log(observation=observation, decision=decision)

        feedback = self._reflect(
            user_input=state.get("user_input", ""),
            observation=observation,
            decision=decision,
        )
        result: NodeUpdate = {
            "reflection_feedback": feedback,
            "reflection_complete": bool(feedback.get("is_complete", self.default_is_complete)),
        }
        if self.merge_feedback_into_observation:
            result["observation"] = {
                "tool_phase": observation,
                "reflection_feedback": feedback,
            }
        if self.emit_memory_update:
            result["memory_updates"] = [self._build_memory_update(state, feedback)]
        return result

    def route(self, state: AgentState) -> str:
        """Routes based on whether reflection considers the turn complete."""
        return self.complete_route if state.get("reflection_complete", self.default_is_complete) else self.incomplete_route

    def _store_reflection_log(self, *, observation: dict[str, Any] | None, decision: Any | None) -> None:
        """Stores a durable reflection record when memory logging is configured."""
        if self.memory_store is None or not observation:
            return
        tool_name = observation.get("tool_name", "unknown")
        output = observation.get("output")
        content = ReflectionMemoryContent(
            reasoning=getattr(decision, "thought", None),
            summary=f"Observed output from tool `{tool_name}`.",
            improvement_suggestions=[],
            failure_analysis=None,
        )
        self.memory_store.add(
            ReflectionMemory(
                layer="warm",
                content=content.model_dump(mode="json"),
                metadata={
                    "agent": self.agent_name,
                    "tags": ["reflection", tool_name],
                    "source": "reflect_node",
                    "priority": "low",
                    "tool_name": tool_name,
                    "llm_name": self._llm_name(),
                    "observation_preview": self._preview_output(output),
                },
            )
        )

    def _reflect(self, *, user_input: str, observation: dict[str, Any] | None, decision: Any | None) -> dict[str, Any]:
        """Builds structured reflection output for the current graph state."""
        if self.llm is None:
            return {
                "reason": self.default_reason if observation or decision else "No reflection context was available.",
                "is_complete": self.default_is_complete,
            }
        rendered_user_prompt = self._render_user_prompt(
            user_prompt=self.user_prompt
            or "User input:\n{user_input}\n\nObservation:\n{observation}\n\nDecision:\n{decision}\n\n"
            "Return JSON with `reason` and `is_complete`.",
            user_input=user_input,
            observation=observation,
            decision=decision,
        )
        raw = self.llm.generate(self.system_prompt or "", rendered_user_prompt).strip()
        return self._parse_payload(raw)

    def _build_memory_update(self, state: AgentState, feedback: dict[str, Any]) -> dict[str, Any]:
        """Builds a reflection-memory update for a later MemoryNode."""
        return {
            "target": "reflection",
            "operation": "store",
            "layer": "warm",
            "content": {
                "summary": feedback.get("reason", self.default_reason),
                "reasoning": {
                    "user_input": state.get("user_input", ""),
                    "decision": self._stringify(state.get("decision")),
                    "observation": self._stringify(state.get("observation")),
                    "is_complete": bool(feedback.get("is_complete", self.default_is_complete)),
                },
            },
            "metadata": {
                "source": "reflect_node",
                "tags": ["reflection", self.agent_name],
                "is_complete": bool(feedback.get("is_complete", self.default_is_complete)),
            },
        }

    def _parse_payload(self, raw: str) -> dict[str, Any]:
        """Parses structured reflection output from the bound llm."""
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match is None:
            return {
                "reason": raw or self.default_reason,
                "is_complete": self.default_is_complete,
            }
        payload = json.loads(match.group(0))
        return {
            "reason": str(payload.get("reason", "")).strip() or self.default_reason,
            "is_complete": bool(payload.get("is_complete", self.default_is_complete)),
        }

    @staticmethod
    def _render_user_prompt(*, user_prompt: str, user_input: str, observation: Any, decision: Any) -> str:
        """Renders reflection prompt text from the current state."""
        rendered = user_prompt
        values = {
            "user_input": ReflectNode._stringify(user_input),
            "observation": ReflectNode._stringify(observation),
            "decision": ReflectNode._stringify(decision),
        }
        for key, value in values.items():
            rendered = rendered.replace(f"{{{key}}}", value)
        return rendered

    @staticmethod
    def _stringify(value: Any) -> str:
        """Serializes arbitrary reflection context into prompt-safe text."""
        try:
            return json.dumps(value, default=str, ensure_ascii=True)
        except TypeError:
            return str(value)

    @staticmethod
    def _preview_output(output: Any) -> str:
        """Builds a short serializable preview of a tool output payload."""
        preview = str(output)
        return preview[:280]
