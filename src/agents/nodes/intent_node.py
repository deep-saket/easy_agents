"""Created: 2026-04-02

Purpose: Implements a reusable intent-classification node for shared agent
graphs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from src.agents.nodes.base import BaseGraphNode
from src.agents.nodes.types import AgentState, NodeUpdate


@dataclass(slots=True)
class IntentNode(BaseGraphNode):
    """Classifies the intent of the current user input.

    This node is intentionally self-sufficient, following the same pattern as
    the shared `ReactNode` and `ResponseNode`:

    - it can be used directly with prompts and an llm
    - it can be subclassed when callers need custom behavior
    - it produces a normalized structured intent payload

    The default llm path expects JSON with:

    - `intent`
    - `confidence`
    - optional `reason`

    When no llm is configured, the node falls back to a minimal deterministic
    classification that labels the input as `default_intent`.
    """

    llm: Any | None = None
    system_prompt: str | None = None
    user_prompt: str | None = None
    intent_labels: list[str] = field(default_factory=list)
    default_intent: str = "unknown"
    default_confidence: float = 0.0

    def classify(
        self,
        *,
        user_input: str,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        intent_labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Builds a structured intent classification for the current input.

        Args:
            user_input: The raw user request.
            system_prompt: Optional node-scoped system prompt override.
            user_prompt: Optional node-scoped user prompt override.
            intent_labels: Optional allowed intent labels for this node.

        Returns:
            A structured intent payload with at least `intent` and
            `confidence`.
        """
        labels = intent_labels if intent_labels is not None else self.intent_labels
        rendered_system_prompt = system_prompt if system_prompt is not None else self.system_prompt
        rendered_user_prompt = self._render_user_prompt(
            user_prompt=user_prompt if user_prompt is not None else (self.user_prompt or "{user_input}"),
            user_input=user_input,
            intent_labels=labels,
        )
        if self.llm is None:
            return {
                "intent": self.default_intent,
                "confidence": self.default_confidence,
                "reason": "IntentNode used its deterministic fallback because no llm was configured.",
            }

        raw = self.llm.generate(rendered_system_prompt or "", rendered_user_prompt).strip()
        return self._parse_intent_payload(raw)

    def execute(self, state: AgentState) -> NodeUpdate:
        """Classifies the current input and writes the result into graph state.

        Args:
            state: The current shared graph state.

        Returns:
            A partial state update containing the normalized intent payload.
        """
        self._record_llm_usage(state, node_name="intent")
        intent = self.classify(
            user_input=state["user_input"],
            system_prompt=self.system_prompt,
            user_prompt=self.user_prompt,
        )
        return {"intent": intent}

    @staticmethod
    def _render_user_prompt(*, user_prompt: str, user_input: str, intent_labels: list[str] | None) -> str:
        """Renders the intent prompt template using input and label context."""
        values = {
            "user_input": user_input,
            "intent_labels": json.dumps(intent_labels or [], ensure_ascii=True),
        }
        rendered_lines: list[str] = []
        for line in user_prompt.splitlines():
            rendered_line = line
            skip_line = False
            for key, value in values.items():
                placeholder = f"{{{key}}}"
                if placeholder not in rendered_line:
                    continue
                if value is None:
                    skip_line = True
                    break
                rendered_line = rendered_line.replace(placeholder, value)
            if skip_line:
                continue
            if re.search(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", rendered_line):
                continue
            rendered_lines.append(rendered_line)
        return "\n".join(rendered_lines).strip() or user_prompt

    def _parse_intent_payload(self, raw: str) -> dict[str, Any]:
        """Parses a JSON intent payload or falls back to a direct label.

        Args:
            raw: Raw llm response text.

        Returns:
            A normalized intent payload.
        """
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {
                "intent": raw or self.default_intent,
                "confidence": self.default_confidence,
                "reason": "IntentNode fell back to using the raw llm output as the intent label.",
            }
        payload = json.loads(match.group(0))
        return {
            "intent": payload.get("intent", self.default_intent),
            "confidence": float(payload.get("confidence", self.default_confidence)),
            "reason": payload.get("reason"),
        }
