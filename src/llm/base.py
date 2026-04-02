"""Created: 2026-03-31

Purpose: Implements the base module for the shared llm platform layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseLLM(ABC):
    """Represents the base l l m component."""
    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError

    @abstractmethod
    def structured_generate(self, prompt: str, schema: type, **kwargs: Any) -> Any:
        raise NotImplementedError
