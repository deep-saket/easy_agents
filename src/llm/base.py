from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseLLM(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError

    @abstractmethod
    def structured_generate(self, prompt: str, schema: type, **kwargs: Any) -> Any:
        raise NotImplementedError
