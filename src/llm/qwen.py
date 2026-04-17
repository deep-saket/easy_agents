"""Created: 2026-03-30

Purpose: Implements the qwen module for the shared llm platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.llm.huggingface import HuggingFaceLLM, LLMGeneration


@dataclass(slots=True)
class Qwen3_1_7BLLM(HuggingFaceLLM):
    """Implements Qwen-specific local inference behavior.

    Qwen reasoning models expose a documented split between `thinking_content`
    and final `content`. The base Hugging Face wrapper supports generic
    reasoning parsing, but Qwen is important enough in this codebase that the
    model-specific split should live here explicitly rather than only through
    inherited configuration.
    """

    model_name: str = "Qwen/Qwen3-1.7B"
    max_new_tokens: int | None = None
    enable_thinking: bool = True
    reasoning_end_token_id: int | None = 151668
    reasoning_end_marker: str | None = "</think>"

    def _parse_generation(self, tokenizer: Any, output_ids: list[int]) -> LLMGeneration:
        """Parses Qwen output into thinking and final answer sections.

        This follows the Qwen reasoning pattern directly:

        1. look for the documented `</think>` token id
        2. fall back to the `</think>` text marker when necessary
        3. clean any residual think-tag markup from the final content

        Args:
            tokenizer: Tokenizer used to decode the generated ids.
            output_ids: Generated token ids excluding the prompt prefix.

        Returns:
            A normalized generation result with `thinking_content` and final
            `content` separated when possible.
        """
        raw_text = tokenizer.decode(output_ids, skip_special_tokens=True).strip()
        split_index = self._find_reasoning_split_index(output_ids)

        if split_index > 0:
            thinking_content = tokenizer.decode(output_ids[:split_index], skip_special_tokens=True).strip()
            content = tokenizer.decode(output_ids[split_index:], skip_special_tokens=True).strip()
        elif self.reasoning_end_marker and self.reasoning_end_marker in raw_text:
            thinking_part, content_part = raw_text.rsplit(self.reasoning_end_marker, 1)
            thinking_content = thinking_part.strip()
            content = content_part.strip()
        else:
            thinking_content = None
            content = raw_text

        if self.reasoning_end_marker and thinking_content:
            thinking_content = thinking_content.replace(self.reasoning_end_marker, "").strip()
        if self.reasoning_end_marker and content.startswith(self.reasoning_end_marker):
            content = content[len(self.reasoning_end_marker) :].strip()
        content = self._strip_residual_reasoning_markup(content)
        if thinking_content == "":
            thinking_content = None

        return LLMGeneration(content=content, thinking_content=thinking_content, raw_text=raw_text)
