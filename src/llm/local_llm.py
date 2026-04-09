"""Created: 2026-03-31

Purpose: Implements the local llm module for the shared llm platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.llm.function_gemma import FunctionGemmaLLM
from src.llm.huggingface import HuggingFaceLLM
from src.llm.base import BaseLLM


@dataclass(slots=True)
class LocalLLM(BaseLLM):
    """Represents the local l l m component."""
    client: HuggingFaceLLM

    def generate(self, prompt: str, **kwargs: Any) -> str:
        system_prompt = kwargs.pop("system_prompt", "You are a helpful local model.")
        user_prompt = kwargs.pop("user_prompt", prompt)
        return self.client.generate(system_prompt, user_prompt)

    def structured_generate(self, prompt: str, schema: type, **kwargs: Any) -> Any:
        system_prompt = kwargs.pop("system_prompt", "Return only structured JSON.")
        user_prompt = kwargs.pop("user_prompt", prompt)
        payload = self.client.generate_json(
            system_prompt,
            self._build_structured_user_prompt(user_prompt, schema),
        )
        print(payload)
        return schema.model_validate(payload)

    @staticmethod
    def _build_structured_user_prompt(user_prompt: str, schema: type) -> str:
        schema_spec = LocalLLM._render_schema_instance_spec(schema)
        return (
            f"{user_prompt}\n\n"
            "Return one JSON object instance with exactly these fields:\n"
            f"{schema_spec}\n\n"
            "Do not return a JSON schema.\n"
            "Do not include keys like `$defs`, `properties`, `required`, `title`, or `type`.\n"
            "Return only the final JSON object."
        )

    @staticmethod
    def _render_schema_instance_spec(schema: type) -> str:
        schema_dict = schema.model_json_schema()
        definitions = schema_dict.get("$defs", {})
        properties = schema_dict.get("properties", {})
        required = set(schema_dict.get("required", []))
        lines: list[str] = []

        for field_name, field_schema in properties.items():
            resolved_schema = LocalLLM._resolve_schema_reference(field_schema, definitions)
            field_type = LocalLLM._describe_schema_type(resolved_schema)
            suffix: list[str] = [field_type]

            enum_values = resolved_schema.get("enum")
            if isinstance(enum_values, list) and enum_values:
                suffix.append("allowed: " + ", ".join(repr(value) for value in enum_values))

            if field_name in required:
                suffix.append("required")
            else:
                suffix.append("optional")

            if "default" in resolved_schema:
                suffix.append(f"default: {resolved_schema['default']!r}")

            lines.append(f'- "{field_name}": ' + "; ".join(suffix))

        return "\n".join(lines)

    @staticmethod
    def _resolve_schema_reference(field_schema: dict[str, Any], definitions: dict[str, Any]) -> dict[str, Any]:
        reference = field_schema.get("$ref")
        if not isinstance(reference, str) or not reference.startswith("#/$defs/"):
            return field_schema
        return definitions.get(reference.split("/")[-1], field_schema)

    @staticmethod
    def _describe_schema_type(field_schema: dict[str, Any]) -> str:
        schema_type = field_schema.get("type")
        if isinstance(schema_type, list):
            return " or ".join(str(item) for item in schema_type)
        if isinstance(schema_type, str):
            return schema_type
        if "enum" in field_schema:
            return "string"
        return "value"


@dataclass(slots=True)
class FunctionCallingLocalLLM(BaseLLM):
    """Represents the function calling local l l m component."""
    client: FunctionGemmaLLM

    def generate(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError("Function-calling local models should be used through structured_generate.")

    def structured_generate(self, prompt: str, schema: type, **kwargs: Any) -> Any:
        payload = self.client.select_tool_call(
            user_input=prompt,
            tool_catalog=kwargs["tool_catalog"],
            memory_state=kwargs.get("memory_state"),
        )
        return schema.model_validate(payload)
