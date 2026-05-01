"""Created: 2026-03-31

Purpose: Implements the factory module for the shared llm platform layer.
"""

from __future__ import annotations

from src.llm.function_gemma import FunctionGemmaLLM
from src.llm.local_llm import FunctionCallingLocalLLM, LocalLLM
from src.llm.qwen import Qwen3_1_7BLLM
from src.llm.remote_llm import GroqLLM, NvidiaLLM, OpenAICompatibleLLM, OpenAILLM, RemoteLLM


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

    @staticmethod
    def build_endpoint_llm(
        endpoint_url: str,
        *,
        model_name: str = "remote-endpoint",
        timeout_seconds: float = 300.0,
        api_key: str | None = None,
        auth_header_name: str = "Authorization",
        auth_scheme: str = "Bearer",
        max_new_tokens: int | None = None,
        default_headers: dict[str, str] | None = None,
        default_body: dict[str, object] | None = None,
    ) -> RemoteLLM:
        return RemoteLLM(
            endpoint_url=endpoint_url,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            api_key=api_key,
            auth_header_name=auth_header_name,
            auth_scheme=auth_scheme,
            max_new_tokens=max_new_tokens,
            default_headers=default_headers or {},
            default_body=default_body or {},
        )

    @staticmethod
    def build_openai_compatible_llm(
        base_url: str,
        *,
        model_name: str,
        api_key: str | None = None,
        timeout_seconds: float = 300.0,
        api_path: str = "/v1/chat/completions",
        max_new_tokens: int | None = None,
        temperature: float | None = None,
        default_headers: dict[str, str] | None = None,
        default_body: dict[str, object] | None = None,
    ) -> OpenAICompatibleLLM:
        return OpenAICompatibleLLM(
            endpoint_url=base_url,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            api_key=api_key,
            max_new_tokens=max_new_tokens,
            default_headers=default_headers or {},
            default_body=default_body or {},
            api_path=api_path,
            temperature=temperature,
        )

    @staticmethod
    def build_openai_llm(
        *,
        model_name: str,
        api_key: str,
        timeout_seconds: float = 300.0,
        api_path: str = "/v1/chat/completions",
        max_new_tokens: int | None = None,
        temperature: float | None = None,
        default_headers: dict[str, str] | None = None,
        default_body: dict[str, object] | None = None,
    ) -> OpenAILLM:
        return OpenAILLM(
            model_name=model_name,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_new_tokens=max_new_tokens,
            default_headers=default_headers or {},
            default_body=default_body or {},
            api_path=api_path,
            temperature=temperature,
        )

    @staticmethod
    def build_nvidia_llm(
        *,
        model_name: str,
        api_key: str,
        base_url: str = "https://integrate.api.nvidia.com",
        timeout_seconds: float = 300.0,
        api_path: str = "/v1/chat/completions",
        max_new_tokens: int | None = None,
        temperature: float | None = None,
        default_headers: dict[str, str] | None = None,
        default_body: dict[str, object] | None = None,
    ) -> NvidiaLLM:
        return NvidiaLLM(
            endpoint_url=base_url,
            model_name=model_name,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_new_tokens=max_new_tokens,
            default_headers=default_headers or {},
            default_body=default_body or {},
            api_path=api_path,
            temperature=temperature,
        )

    @staticmethod
    def build_groq_llm(
        *,
        model_name: str,
        api_key: str,
        timeout_seconds: float = 300.0,
        api_path: str = "/v1/chat/completions",
        max_new_tokens: int | None = None,
        temperature: float | None = None,
        default_headers: dict[str, str] | None = None,
        default_body: dict[str, object] | None = None,
    ) -> GroqLLM:
        return GroqLLM(
            model_name=model_name,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_new_tokens=max_new_tokens,
            default_headers=default_headers or {},
            default_body=default_body or {},
            api_path=api_path,
            temperature=temperature,
        )
