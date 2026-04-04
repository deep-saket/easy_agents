"""Created: 2026-03-31

Purpose: Implements the function gemma module for the shared llm platform layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from src.platform_logging.tracing import record_llm_call
from src.schemas.tool_io import ToolCall


@dataclass(slots=True)
class FunctionGemmaLLM:
    """Represents the function gemma l l m component."""
    model_name: str = "google/functiongemma-270m-it"
    device_map: str = "auto"
    torch_dtype: str = "auto"
    max_new_tokens: int = 128
    _processor: Any = field(default=None, init=False, repr=False)
    _model: Any = field(default=None, init=False, repr=False)

    def select_tool_call(
        self,
        *,
        user_input: str,
        tool_catalog: list[dict[str, Any]],
        memory_state: dict[str, object] | None = None,
    ) -> ToolCall:
        started = perf_counter()
        processor = self._get_processor()
        model = self._get_model()
        message = [
            {
                "role": "developer",
                "content": "You are a model that can do function calling with the following functions.",
            },
            {
                "role": "user",
                "content": self._build_user_prompt(user_input=user_input, memory_state=memory_state or {}),
            },
        ]
        inputs = processor.apply_chat_template(
            message,
            tools=tool_catalog,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        outputs = model.generate(
            **inputs.to(model.device),
            pad_token_id=processor.eos_token_id,
            max_new_tokens=self.max_new_tokens,
        )
        output_ids = outputs[0][len(inputs["input_ids"][0]) :]
        content = processor.decode(output_ids, skip_special_tokens=True)
        prompt_tokens = int(inputs["input_ids"].shape[-1])
        completion_tokens = int(output_ids.shape[-1])
        total_tokens = prompt_tokens + completion_tokens
        record_llm_call(
            model_name=self.model_name,
            call_kind="tool_selection",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=round((perf_counter() - started) * 1000, 3),
        )
        return self._parse_function_call(content)

    @staticmethod
    def _build_user_prompt(*, user_input: str, memory_state: dict[str, object]) -> str:
        if not memory_state:
            return user_input
        return f"User input: {user_input}\nConversation state: {memory_state}"

    @staticmethod
    def _parse_function_call(content: str) -> ToolCall:
        match = re.search(r"call:([a-zA-Z0-9_]+)\{(.*)\}", content)
        if not match:
            raise ValueError(f"Function Gemma did not return a function call: {content}")
        tool_name = match.group(1)
        argument_block = match.group(2).strip()
        arguments: dict[str, Any] = {}
        if argument_block:
            pairs = re.findall(r"([a-zA-Z0-9_]+):(?:<escape>)?(.*?)(?:<escape>)?(?=,\s*[a-zA-Z0-9_]+:|$)", argument_block)
            for key, value in pairs:
                cleaned = value.strip().strip(",").strip()
                if cleaned.lower() == "true":
                    arguments[key] = True
                elif cleaned.lower() == "false":
                    arguments[key] = False
                else:
                    arguments[key] = cleaned
        return ToolCall(tool_name=tool_name, arguments=arguments)

    def _get_processor(self) -> Any:
        if self._processor is None:
            try:
                from transformers import AutoProcessor
            except ImportError as exc:
                raise RuntimeError(
                    "transformers is required for Function Gemma tool selection. Install with `pip install -e '.[local-llm]'`."
                ) from exc
            self._processor = AutoProcessor.from_pretrained(self.model_name, device_map=self.device_map)
        return self._processor

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from transformers import AutoModelForCausalLM
            except ImportError as exc:
                raise RuntimeError(
                    "transformers is required for Function Gemma tool selection. Install with `pip install -e '.[local-llm]'`."
                ) from exc
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                torch_dtype=self.torch_dtype,
                device_map=self.device_map,
            )
        return self._model
