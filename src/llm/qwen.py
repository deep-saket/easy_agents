"""Created: 2026-03-30

Purpose: Implements the qwen module for the shared llm platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from llm.huggingface import HuggingFaceLLM


@dataclass(slots=True)
class Qwen3_1_7BLLM(HuggingFaceLLM):
    model_name: str = "Qwen/Qwen3-1.7B"
    max_new_tokens: int = 512
    enable_thinking: bool = True
    reasoning_end_token_id: int | None = 151668
    reasoning_end_marker: str | None = "</think>"
