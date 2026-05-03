"""Structured LLM JSON utilities for collection agents.

Purpose: centralize robust JSON extraction/validation with bounded retries.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError


class StructuredOutputError(RuntimeError):
    """Raised when a structured LLM response cannot be validated."""

    pass


class StructuredOutputRunner:
    """Runs LLM prompts and validates JSON output against a schema.

    Retry strategy:
    1) use `structured_generate` when available
    2) else use `generate_json` when available
    3) else use `generate` + JSON extraction
    4) on parse/validation failure, ask for strict JSON repair
    """

    def __init__(self, llm: Any, *, max_retries: int = 2) -> None:
        self.llm = llm
        self.max_retries = max(0, int(max_retries))

    def run(self, *, system_prompt: str, user_prompt: str, schema: type[BaseModel]) -> BaseModel:
        if self.llm is None:
            raise StructuredOutputError("LLM is not configured.")

        attempt = 0
        last_error: Exception | None = None
        last_raw: str = ""

        while attempt <= self.max_retries:
            try:
                return self._single_call(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    schema=schema,
                    previous_raw=(last_raw if attempt > 0 else ""),
                )
            except Exception as exc:  # pragma: no cover - defensive path
                last_error = exc
                last_raw = str(exc)
                attempt += 1

        raise StructuredOutputError(f"Structured output failed after retries: {last_error}")

    def _single_call(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[BaseModel],
        previous_raw: str,
    ) -> BaseModel:
        prompt = user_prompt
        if previous_raw:
            prompt = (
                f"{user_prompt}\n\n"
                "Your previous output could not be parsed/validated. "
                "Return only valid JSON matching the schema. "
                f"Previous output/error: {previous_raw}"
            )

        if hasattr(self.llm, "structured_generate"):
            try:
                value = self.llm.structured_generate(prompt, schema, system_prompt=system_prompt)
                if isinstance(value, schema):
                    return value
                if isinstance(value, BaseModel):
                    return schema.model_validate(value.model_dump(mode="json"))
                if isinstance(value, dict):
                    return schema.model_validate(value)
                return schema.model_validate_json(json.dumps(value, ensure_ascii=True, default=str))
            except ValidationError:
                raise
            except Exception:
                # fall through to other routes
                pass

        if hasattr(self.llm, "generate_json"):
            payload = self.llm.generate_json(system_prompt, prompt)
            return schema.model_validate(payload)

        if not hasattr(self.llm, "generate"):
            raise StructuredOutputError("LLM does not support generate/structured_generate/generate_json.")

        raw = str(self.llm.generate(system_prompt, prompt)).strip()
        json_text = self._extract_json_object(raw)
        payload = json.loads(json_text)
        if not isinstance(payload, dict):
            raise StructuredOutputError("Structured output must be a JSON object.")
        return schema.model_validate(payload)

    @staticmethod
    def _extract_json_object(text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\\s*```$", "", cleaned)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise StructuredOutputError("Model did not return a JSON object.")
        return cleaned[start : end + 1]


__all__ = ["StructuredOutputRunner", "StructuredOutputError"]
