"""Collection-specific intent node with namespaced state output keys."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from agents.collection_agent.llm_structured import StructuredOutputRunner
from src.nodes.intent_node import IntentNode
from src.nodes.types import AgentState, NodeUpdate


class _IntentPayload(BaseModel):
    intent: str
    confidence: float = Field(default=0.0)
    reason: str | None = None


@dataclass(slots=True)
class CollectionIntentNode(IntentNode):
    """Writes and routes intent payloads using a dedicated state key."""

    output_key: str = "intent"
    allow_deterministic_fallback: bool = False

    def classify(
        self,
        *,
        user_input: str,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        intent_labels: list[str] | None = None,
    ) -> dict[str, Any]:
        labels = intent_labels if intent_labels is not None else self.intent_labels
        rendered_system_prompt = system_prompt if system_prompt is not None else self.system_prompt
        rendered_user_prompt = self._render_user_prompt(
            user_prompt=user_prompt if user_prompt is not None else (self.user_prompt or "{user_input}"),
            user_input=user_input,
            intent_labels=labels,
        )

        if self.llm is None:
            return self._deterministic_classify(user_input=user_input, labels=labels)

        try:
            runner = StructuredOutputRunner(self.llm, max_retries=2)
            payload = runner.run(
                system_prompt=rendered_system_prompt or "",
                user_prompt=rendered_user_prompt,
                schema=_IntentPayload,
            )
            intent_name = self._normalize_intent_name(payload.intent)
            if labels and intent_name not in {self._normalize_intent_name(v) for v in labels}:
                raise ValueError(f"Intent `{payload.intent}` is not in allowed labels: {labels}")
            return {
                "intent": intent_name or self.default_intent,
                "confidence": float(payload.confidence),
                "reason": payload.reason,
            }
        except Exception as exc:
            if not self.allow_deterministic_fallback:
                raise RuntimeError(
                    "CollectionIntentNode failed to produce structured LLM intent output. "
                    f"Fallback disabled. Error: {exc}"
                ) from exc
            return self._deterministic_classify(user_input=user_input, labels=labels)

    def execute(self, state: AgentState) -> NodeUpdate:
        self._record_llm_usage(state, node_name="intent")
        if self.llm is None and not self.allow_deterministic_fallback:
            raise RuntimeError(
                "CollectionIntentNode requires an active LLM. "
                "Deterministic intent fallback is disabled for collection agent."
            )
        intent = self.classify(
            user_input=state["user_input"],
            system_prompt=self.system_prompt,
            user_prompt=self.user_prompt,
        )
        update: NodeUpdate = {
            self.output_key: intent,
            # Compatibility channel for shared routing assumptions in existing
            # graph/runtime reducers. This can be removed after full migration.
            "intent": intent,
        }
        intent_name = self._normalize_intent_name(intent.get("intent") if isinstance(intent, dict) else None)
        mapped_response = self._lookup_mapped_value(self.response_map, intent_name)
        if mapped_response is not None:
            update["response"] = mapped_response
        return update

    def route(self, state: AgentState) -> str:
        intent_payload = state.get(self.output_key)
        if intent_payload is None:
            intent_payload = state.get("intent")
        intent_name = None
        if isinstance(intent_payload, dict):
            intent_name = intent_payload.get("intent")
        normalized = self._normalize_intent_name(intent_name)
        route = self._lookup_mapped_value(self.route_map, normalized)
        return route if route is not None else self.default_route
