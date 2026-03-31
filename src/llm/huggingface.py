from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LLMGeneration:
    content: str
    thinking_content: str | None = None
    raw_text: str = ""


@dataclass(slots=True)
class HuggingFaceLLM:
    model_name: str
    device_map: str = "auto"
    torch_dtype: str = "auto"
    max_new_tokens: int = 384
    enable_thinking: bool = False
    reasoning_end_token_id: int | None = None
    reasoning_end_marker: str | None = None
    _tokenizer: Any = field(default=None, init=False, repr=False)
    _model: Any = field(default=None, init=False, repr=False)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return self.generate_result(system_prompt, user_prompt).content

    def generate_result(self, system_prompt: str, user_prompt: str) -> LLMGeneration:
        tokenizer = self._get_tokenizer()
        model = self._get_model()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            prompt_text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=self.enable_thinking,
            )
        except TypeError:
            prompt_text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        model_inputs = tokenizer([prompt_text], return_tensors="pt").to(model.device)
        generated_ids = model.generate(**model_inputs, max_new_tokens=self.max_new_tokens)
        output_ids = generated_ids[0][len(model_inputs.input_ids[0]) :].tolist()
        return self._parse_generation(tokenizer, output_ids)

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = self.generate_result(system_prompt, user_prompt).content
        start = response.find("{")
        end = response.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("Model did not return a JSON object.")
        return json.loads(response[start : end + 1])

    def _parse_generation(self, tokenizer: Any, output_ids: list[int]) -> LLMGeneration:
        raw_text = tokenizer.decode(output_ids, skip_special_tokens=True).strip()
        thinking_content: str | None = None
        content = raw_text

        split_index = self._find_reasoning_split_index(output_ids)
        if split_index > 0:
            thinking_content = tokenizer.decode(output_ids[:split_index], skip_special_tokens=True).strip()
            content = tokenizer.decode(output_ids[split_index:], skip_special_tokens=True).strip()
        elif self.reasoning_end_marker and self.reasoning_end_marker in raw_text:
            thinking_part, content_part = raw_text.rsplit(self.reasoning_end_marker, 1)
            thinking_content = thinking_part.strip()
            content = content_part.strip()

        if self.reasoning_end_marker and content.startswith(self.reasoning_end_marker):
            content = content[len(self.reasoning_end_marker) :].strip()
        if thinking_content == "":
            thinking_content = None

        return LLMGeneration(content=content, thinking_content=thinking_content, raw_text=raw_text)

    def _find_reasoning_split_index(self, output_ids: list[int]) -> int:
        if self.reasoning_end_token_id is None:
            return 0
        try:
            return len(output_ids) - output_ids[::-1].index(self.reasoning_end_token_id)
        except ValueError:
            return 0

    def _get_tokenizer(self) -> Any:
        if self._tokenizer is None:
            try:
                from transformers import AutoTokenizer
            except ImportError as exc:
                raise RuntimeError(
                    "transformers is required for local Hugging Face inference. Install with `pip install -e '.[local-llm]'`."
                ) from exc
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        return self._tokenizer

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from transformers import AutoModelForCausalLM
            except ImportError as exc:
                raise RuntimeError(
                    "transformers is required for local Hugging Face inference. Install with `pip install -e '.[local-llm]'`."
                ) from exc
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                torch_dtype=self.torch_dtype,
                device_map=self.device_map,
            )
        return self._model
