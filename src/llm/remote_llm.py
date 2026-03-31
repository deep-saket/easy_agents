"""Created: 2026-03-31

Purpose: Implements the remote llm module for the shared llm platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from llm.base import BaseLLM


@dataclass(slots=True)
class RemoteLLM(BaseLLM):
    provider: str = "unconfigured"

    def generate(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError("Remote LLM integration is a future platform extension.")

    def structured_generate(self, prompt: str, schema: type, **kwargs: Any) -> Any:
        raise NotImplementedError("Remote LLM integration is a future platform extension.")
