from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class HuggingFaceLLM:
    model_name: str
    device_map: str = "auto"
    torch_dtype: str = "auto"
    max_new_tokens: int = 384
    enable_thinking: bool = False
    _tokenizer: Any = field(default=None, init=False, repr=False)
    _model: Any = field(default=None, init=False, repr=False)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
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
        output_ids = generated_ids[0][len(model_inputs.input_ids[0]) :]
        return tokenizer.decode(output_ids, skip_special_tokens=True).strip()

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = self.generate(system_prompt, user_prompt)
        start = response.find("{")
        end = response.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("Model did not return a JSON object.")
        return json.loads(response[start : end + 1])

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

