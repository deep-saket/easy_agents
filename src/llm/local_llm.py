"""Created: 2026-03-31

Purpose: Implements the local llm module for the shared llm platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from llm.function_gemma import FunctionGemmaLLM
from llm.huggingface import HuggingFaceLLM
from llm.base import BaseLLM


@dataclass(slots=True)
class LocalLLM(BaseLLM):
    client: HuggingFaceLLM

    def generate(self, prompt: str, **kwargs: Any) -> str:
        system_prompt = kwargs.pop("system_prompt", "You are a helpful local model.")
        return self.client.generate(system_prompt, prompt)

    def structured_generate(self, prompt: str, schema: type, **kwargs: Any) -> Any:
        system_prompt = kwargs.pop("system_prompt", "Return only structured JSON.")
        payload = self.client.generate_json(system_prompt, prompt)
        return schema.model_validate(payload)


@dataclass(slots=True)
class FunctionCallingLocalLLM(BaseLLM):
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
