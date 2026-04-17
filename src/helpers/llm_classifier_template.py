"""Created: 2026-04-05

Purpose: Provides a reusable prompt-driven LLM classification template for the
shared framework layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

PayloadT = TypeVar("PayloadT", bound=BaseModel)


class GenericClassificationOutput(BaseModel):
    """Represents a minimal structured classification result."""

    label: str
    reason: str
    confidence: float | None = None
    class_probabilities: dict[str, float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenericMultiLabelClassificationOutput(BaseModel):
    """Represents a minimal structured multi-label classification result."""

    labels: list[str]
    reason: str
    confidence: float | None = None
    class_probabilities: dict[str, float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class LLMClassifierTemplate(Generic[PayloadT]):
    """Runs prompt-driven structured classification against an LLM."""

    llm: Any
    system_prompt: str
    user_prompt: str
    classification_classes: list[str]
    class_details: dict[str, Any]
    output_schema: type[PayloadT]
    multi_label: bool = False
    calc_prob: bool = False

    def classify(self, payload: dict[str, Any] | BaseModel) -> PayloadT:
        """Classifies an input payload into the configured structured schema."""

        rendered_system_prompt = self.system_prompt.format(
            classification_classes_json=self._to_json(self.classification_classes),
            class_details_json=self._to_json(self.class_details),
            classification_mode="multi_label" if self.multi_label else "single_label",
            calc_prob=self.calc_prob,
        )
        rendered_user_prompt = self.user_prompt.format(
            input_json=self._to_json(payload),
            classification_classes_json=self._to_json(self.classification_classes),
            class_details_json=self._to_json(self.class_details),
            classification_mode="multi_label" if self.multi_label else "single_label",
            calc_prob=self.calc_prob,
        )
        rendered_system_prompt = self._append_mode_instruction(rendered_system_prompt)
        rendered_user_prompt = self._append_mode_instruction(rendered_user_prompt)
        return self._generate_structured(
            system_prompt=rendered_system_prompt,
            user_prompt=rendered_user_prompt,
        )

    def _generate_structured(self, *, system_prompt: str, user_prompt: str) -> PayloadT:
        if hasattr(self.llm, "structured_generate"):
            validated = self.llm.structured_generate(
                user_prompt,
                self.output_schema,
                system_prompt=system_prompt,
            )
            return self._validate_model(validated)
        if hasattr(self.llm, "generate_json"):
            payload = self.llm.generate_json(system_prompt, user_prompt)
            return self._validate_payload(payload)
        if hasattr(self.llm, "generate"):
            response = self.llm.generate(system_prompt, user_prompt)
            return self._validate_payload(json.loads(self._extract_json(response)))
        raise TypeError("LLMClassifierTemplate requires an llm with structured_generate, generate_json, or generate.")

    def _validate_payload(self, payload: dict[str, Any]) -> PayloadT:
        validated = self.output_schema.model_validate(payload)
        return self._validate_model(validated)

    def _validate_model(self, validated: PayloadT) -> PayloadT:
        if self.multi_label and not hasattr(validated, "labels"):
            raise ValueError("multi_label=True requires an output schema with a `labels` field.")
        if not self.multi_label and not hasattr(validated, "label") and not hasattr(validated, "category"):
            raise ValueError("single-label classification requires an output schema with `label` or domain-specific equivalent.")
        if self.calc_prob:
            probabilities = getattr(validated, "class_probabilities", None)
            if probabilities is None:
                raise ValueError("calc_prob=True requires an output schema with `class_probabilities`.")
            if not isinstance(probabilities, dict) or not probabilities:
                raise ValueError("`class_probabilities` must be a non-empty mapping when calc_prob=True.")
            for label, probability in probabilities.items():
                if label not in self.classification_classes:
                    raise ValueError(f"Probability provided for unknown class `{label}`.")
                if not 0.0 <= float(probability) <= 1.0:
                    raise ValueError("Class probabilities must be between 0 and 1.")
            if self.multi_label:
                labels = getattr(validated, "labels", [])
                missing = [label for label in labels if label not in probabilities]
                if missing:
                    raise ValueError("calc_prob=True requires probabilities for every returned label.")
            else:
                single_label = getattr(validated, "label", getattr(validated, "category", None))
                normalized_label = getattr(single_label, "value", single_label)
                if normalized_label not in probabilities:
                    raise ValueError("calc_prob=True requires a probability entry for the selected class.")
        return validated

    def _to_json(self, payload: dict[str, Any] | BaseModel | list[str]) -> str:
        if isinstance(payload, BaseModel):
            raw = payload.model_dump(mode="json")
        else:
            raw = payload
        return json.dumps(raw, indent=2, sort_keys=True, default=self._json_default)

    def _append_mode_instruction(self, prompt: str) -> str:
        lines = [prompt, ""]
        if self.multi_label:
            lines.extend(
                [
                    "Classification mode: multi_label.",
                    "Return all applicable classes in a `labels` array.",
                ]
            )
        else:
            lines.extend(
                [
                    "Classification mode: single_label.",
                    "Return exactly one best class in a `label` field unless the domain schema uses a different single-class field.",
                ]
            )
        if self.calc_prob:
            lines.extend(
                [
                    "Probability mode: enabled.",
                    "Return `class_probabilities` as independent probabilities for the classified classes.",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def _extract_json(response: str) -> str:
        start = response.find("{")
        end = response.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("Model did not return a JSON object.")
        return response[start : end + 1]

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        if hasattr(value, "value"):
            return value.value
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable.")
