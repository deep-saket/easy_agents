"""Created: 2026-03-31

Purpose: Implements the factory module for the shared llm platform layer.
"""

from __future__ import annotations

from llm.function_gemma import FunctionGemmaLLM
from llm.qwen import Qwen3_1_7BLLM
from llm.local_llm import FunctionCallingLocalLLM, LocalLLM


class LLMFactory:
    @staticmethod
    def build_default_local_llm(model_name: str = "Qwen/Qwen3-1.7B") -> LocalLLM:
        return LocalLLM(client=Qwen3_1_7BLLM(model_name=model_name))

    @staticmethod
    def build_function_calling_llm(model_name: str = "google/functiongemma-270m-it") -> FunctionCallingLocalLLM:
        return FunctionCallingLocalLLM(client=FunctionGemmaLLM(model_name=model_name))
