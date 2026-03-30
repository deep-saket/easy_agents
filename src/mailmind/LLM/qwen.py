from __future__ import annotations

from dataclasses import dataclass

from mailmind.LLM.huggingface import HuggingFaceLLM


@dataclass(slots=True)
class Qwen3_1_7BLLM(HuggingFaceLLM):
    model_name: str = "Qwen/Qwen3-1.7B"
    max_new_tokens: int = 512
    enable_thinking: bool = False

