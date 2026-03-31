"""Local LLM clients."""

from LLM.huggingface import HuggingFaceLLM
from LLM.qwen import Qwen3_1_7BLLM

__all__ = ["HuggingFaceLLM", "Qwen3_1_7BLLM"]
