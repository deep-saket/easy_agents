"""Created: 2026-03-30

Purpose: Implements the huggingface module for the shared llm platform layer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

from src.llm.base import BaseLLM
from src.platform_logging.tracing import record_llm_call

@dataclass(slots=True)
class LLMGeneration:
    """Represents the l l m generation component."""
    content: str
    thinking_content: str | None = None
    raw_text: str = ""


@dataclass(slots=True)
class HuggingFaceLLM(BaseLLM):
    """Represents the hugging face l l m component."""
    model_name: str
    device_map: str = "auto"
    torch_dtype: str = "auto"
    max_new_tokens: int | None = None
    use_kv_chache: bool = False
    debug_prompt_path: str | None = None
    enable_thinking: bool = False
    reasoning_end_token_id: int | None = None
    reasoning_end_marker: str | None = None
    _tokenizer: Any = field(default=None, init=False, repr=False)
    _model: Any = field(default=None, init=False, repr=False)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return self.generate_result(system_prompt, user_prompt).content

    def generate_result(self, system_prompt: str, user_prompt: str) -> LLMGeneration:
        started = perf_counter()
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
        self._save_debug_prompt(prompt_text)
        model_inputs = tokenizer([prompt_text], return_tensors="pt").to(model.device)
        prompt_tokens = int(model_inputs["input_ids"].shape[-1])
        max_new_tokens = self._resolve_max_new_tokens(
            model=model,
            prompt_tokens=prompt_tokens,
            tokenizer=tokenizer,
        )
        if self.use_kv_chache:
            output_ids = self._generate_output_ids_with_kv_cache(
                model=model,
                tokenizer=tokenizer,
                model_inputs=model_inputs,
                max_new_tokens=max_new_tokens,
            )
        else:
            output_ids = self._generate_output_ids(
                model=model,
                tokenizer=tokenizer,
                model_inputs=model_inputs,
                max_new_tokens=max_new_tokens,
            )
        completion_tokens = len(output_ids)
        total_tokens = prompt_tokens + completion_tokens
        record_llm_call(
            model_name=self.model_name,
            call_kind="generate",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=round((perf_counter() - started) * 1000, 3),
        )
        return self._parse_generation(tokenizer, output_ids)

    def _save_debug_prompt(self, prompt_text: str) -> None:
        if not self.debug_prompt_path:
            return
        Path(self.debug_prompt_path).write_text(prompt_text, encoding="utf-8")

    def _generate_output_ids(
        self,
        *,
        model: Any,
        tokenizer: Any,
        model_inputs: Any,
        max_new_tokens: int,
    ) -> list[int]:
        eos_token_id = getattr(tokenizer, "eos_token_id", None)
        if eos_token_id is None:
            eos_token_id = getattr(getattr(model, "config", None), "eos_token_id", None)

        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=max_new_tokens,
            use_cache=False,
            eos_token_id=eos_token_id,
            pad_token_id=getattr(tokenizer, "pad_token_id", eos_token_id),
        )
        return generated_ids[0, model_inputs["input_ids"].shape[-1] :].tolist()

    def _generate_output_ids_with_kv_cache(
        self,
        *,
        model: Any,
        tokenizer: Any,
        model_inputs: Any,
        max_new_tokens: int,
    ) -> list[int]:
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError(
                "torch is required for local Hugging Face inference. Install with `pip install -e '.[local-llm]'`."
            ) from exc

        generated_token_ids: list[int] = []
        next_inputs = model_inputs
        eos_token_ids = self._eos_token_ids(model=model, tokenizer=tokenizer)
        for _ in range(max_new_tokens):
            with torch.no_grad():
                outputs = model.__call__(**next_inputs, use_cache=True)

            next_token_id = int(outputs.logits[0, -1, :].argmax(dim=-1).item())
            decoded_token = tokenizer.decode([next_token_id], skip_special_tokens=False)
            print(f"iteration : {_} | next_token_id: {next_token_id} | decoded: {decoded_token!r}")

            generated_token_ids.append(next_token_id)
            if next_token_id in eos_token_ids:
                break

            attention_mask = next_inputs["attention_mask"]
            next_inputs = {
                "input_ids": torch.tensor([[next_token_id]], dtype=next_inputs["input_ids"].dtype, device=model.device),
                "attention_mask": torch.cat(
                    [
                        attention_mask,
                        torch.ones((attention_mask.shape[0], 1), dtype=attention_mask.dtype, device=attention_mask.device),
                    ],
                    dim=1,
                ),
                "past_key_values": outputs.past_key_values,
            }


        return generated_token_ids

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = self.generate_result(system_prompt, user_prompt).content
        candidate = self._extract_json_object(response)
        return self._load_dirty_json(candidate)

    def structured_generate(self, prompt: str, schema: type, **kwargs: Any) -> Any:
        system_prompt = kwargs.pop("system_prompt", "Return only structured JSON.")
        payload = self.generate_json(system_prompt, prompt)
        return schema.model_validate(payload)

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
        content = self._strip_residual_reasoning_markup(content)
        if thinking_content == "":
            thinking_content = None

        return LLMGeneration(content=content, thinking_content=thinking_content, raw_text=raw_text)

    @staticmethod
    def _extract_json_object(response: str) -> str:
        cleaned = response.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        start = cleaned.find("{")
        if start == -1:
            raise ValueError("Model did not return a JSON object.")

        in_string = False
        escape = False
        depth = 0
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return cleaned[start : index + 1]
        raise ValueError("Model did not return a complete JSON object.")

    @classmethod
    def _load_dirty_json(cls, candidate: str) -> dict[str, Any]:
        repaired = candidate.strip()
        repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)

        for _ in range(8):
            try:
                parsed = json.loads(repaired)
                if not isinstance(parsed, dict):
                    raise ValueError("Model did not return a JSON object.")
                return parsed
            except json.JSONDecodeError as exc:
                updated = cls._repair_json_candidate(repaired, exc)
                if updated == repaired:
                    raise
                repaired = updated

        parsed = json.loads(repaired)
        if not isinstance(parsed, dict):
            raise ValueError("Model did not return a JSON object.")
        return parsed

    @staticmethod
    def _repair_json_candidate(candidate: str, exc: json.JSONDecodeError) -> str:
        if exc.msg == "Extra data":
            return candidate[: exc.pos].rstrip()
        if "Expecting ',' delimiter" in exc.msg:
            position = exc.pos
            while position > 0 and candidate[position - 1].isspace():
                position -= 1
            if position > 0 and candidate[position - 1] not in ",[{:":
                    return candidate[:position] + "," + candidate[position:]
        return candidate

    @staticmethod
    def _eos_token_ids(*, model: Any, tokenizer: Any) -> set[int]:
        eos_token_ids: set[int] = set()
        tokenizer_eos = getattr(tokenizer, "eos_token_id", None)
        if isinstance(tokenizer_eos, int):
            eos_token_ids.add(tokenizer_eos)
        config_eos = getattr(getattr(model, "config", None), "eos_token_id", None)
        if isinstance(config_eos, int):
            eos_token_ids.add(config_eos)
        elif isinstance(config_eos, (list, tuple, set)):
            eos_token_ids.update(token for token in config_eos if isinstance(token, int))
        return eos_token_ids

    def _resolve_max_new_tokens(self, *, model: Any, prompt_tokens: int, tokenizer: Any) -> int:
        if self.max_new_tokens is not None:
            return self.max_new_tokens

        context_limit = getattr(getattr(model, "config", None), "max_position_embeddings", None)
        if not isinstance(context_limit, int) or context_limit <= 0:
            tokenizer_limit = getattr(tokenizer, "model_max_length", None)
            if isinstance(tokenizer_limit, int) and 0 < tokenizer_limit < 10**9:
                context_limit = tokenizer_limit

        if isinstance(context_limit, int) and context_limit > prompt_tokens:
            return max(1, context_limit - prompt_tokens)
        return 512

    @staticmethod
    def _strip_residual_reasoning_markup(content: str) -> str:
        """Removes leaked reasoning tags from a model response.

        Some local reasoning models may still emit `<think>` blocks into the
        final content when the end marker is missing or malformed. That is safe
        for plain chat, but it breaks downstream tool calls that expect clean
        structured text such as SQL, JSON, or arithmetic expressions.

        Args:
            content: The decoded content portion after the primary reasoning
                split logic has run.

        Returns:
            Content with leading think-tag markup removed as defensively as
            possible while preserving the actual answer text.
        """
        original = content.strip()
        cleaned = re.sub(r"(?is)^<think>\s*", "", original).strip()
        cleaned = re.sub(r"(?is)</?think>\s*", "", cleaned).strip()
        if original.startswith("<think>") and "</think>" not in original:
            lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
            return lines[-1] if lines else cleaned
        if "<think>" not in cleaned and "</think>" not in cleaned:
            return cleaned
        parts = re.split(r"(?is)</think>", content, maxsplit=1)
        if len(parts) == 2:
            return parts[1].strip()
        lines = [
            line.strip()
            for line in cleaned.splitlines()
            if line.strip() and not line.strip().startswith("<think>")
        ]
        return lines[-1] if lines else cleaned

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
