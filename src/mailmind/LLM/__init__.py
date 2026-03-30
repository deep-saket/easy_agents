"""Local LLM clients."""

from mailmind.LLM.huggingface import HuggingFaceLLM
from mailmind.LLM.qwen import Qwen3_1_7BLLM

__all__ = ["HuggingFaceLLM", "Qwen3_1_7BLLM"]

