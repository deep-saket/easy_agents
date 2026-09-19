"""Compatibility exports for both ``src.llm`` and installed ``llm`` imports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "BaseLLM",
    "FunctionCallingLocalLLM",
    "EndpointLLM",
    "GroqLLM",
    "LLMFactory",
    "LocalLLM",
    "MacGemmaError",
    "MacGemmaLLM",
    "NvidiaLLM",
    "OpenAICompatibleLLM",
    "OpenAILLM",
    "RemoteLLM",
]

_EXPORT_MODULES = {
    "BaseLLM": ".base",
    "FunctionCallingLocalLLM": ".local_llm",
    "EndpointLLM": ".remote_llm",
    "GroqLLM": ".remote_llm",
    "LLMFactory": ".factory",
    "LocalLLM": ".local_llm",
    "MacGemmaError": ".mac_gemma",
    "MacGemmaLLM": ".mac_gemma",
    "NvidiaLLM": ".remote_llm",
    "OpenAICompatibleLLM": ".remote_llm",
    "OpenAILLM": ".remote_llm",
    "RemoteLLM": ".remote_llm",
}


def __getattr__(name: str) -> Any:
    """Loads public adapters lazily so optional backends stay optional."""

    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value
