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
