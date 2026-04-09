"""Created: 2026-03-31

Purpose: Implements the factory module for the shared llm platform layer.
"""

from __future__ import annotations

from src.llm.function_gemma import FunctionGemmaLLM
from src.llm.qwen import Qwen3_1_7BLLM
from src.llm.local_llm import FunctionCallingLocalLLM, LocalLLM


class LLMFactory:
    """Represents the l l m factory component."""
    _QWEN_3_1_7B_ALIASES: tuple[str, ...] = ("Qwen3-1.7B", "Qwen/Qwen3-1.7B")

    @staticmethod
    def build_default_local_llm(
        model_name: str = "Qwen3-1.7B",
        *,
        device_map: str = "auto",
        torch_dtype: str = "auto",
        max_new_tokens: int | None = None,
        enable_thinking: bool = True,
        use_kv_chache: bool = False,
    ) -> LocalLLM:
        if model_name in LLMFactory._QWEN_3_1_7B_ALIASES:
            resolved_model_name = "Qwen/Qwen3-1.7B"
            return LocalLLM(
                client=Qwen3_1_7BLLM(
                    model_name=resolved_model_name,
                    device_map=device_map,
                    torch_dtype=torch_dtype,
                    max_new_tokens=max_new_tokens,
                    enable_thinking=enable_thinking,
                    use_kv_chache=use_kv_chache,
                )
            )
        raise ValueError(f"Unsupported default local model: {model_name}")

    @staticmethod
    def build_function_calling_llm(
        model_name: str = "google/functiongemma-270m-it",
        *,
        device_map: str = "auto",
        torch_dtype: str = "auto",
        max_new_tokens: int | None = None,
    ) -> FunctionCallingLocalLLM:
        return FunctionCallingLocalLLM(
            client=FunctionGemmaLLM(
                model_name=model_name,
                device_map=device_map,
                torch_dtype=torch_dtype,
                max_new_tokens=max_new_tokens,
            )
        )
