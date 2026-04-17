"""Created: 2026-03-31

Purpose: Implements the base module for the shared llm platform layer.
"""

from __future__ import annotations

import inspect
from abc import ABC, ABCMeta, abstractmethod
from typing import Any


class SingletonABCMeta(ABCMeta):
    """Caches one LLM instance per subclass and constructor configuration."""

    _instances: dict[tuple[type, tuple[tuple[str, object], ...]], object] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> object:
        key = (cls, cls._singleton_cache_key(*args, **kwargs))
        if key not in cls._instances:
            cls._instances[key] = super().__call__(*args, **kwargs)
        return cls._instances[key]

    def _singleton_cache_key(cls, *args: Any, **kwargs: Any) -> tuple[tuple[str, object], ...]:
        signature = inspect.signature(cls.__init__)
        bound = signature.bind_partial(None, *args, **kwargs)
        bound.apply_defaults()
        normalized_items: list[tuple[str, object]] = []
        for name, value in bound.arguments.items():
            if name == "self":
                continue
            normalized_items.append((name, cls._normalize_singleton_value(value)))
        return tuple(normalized_items)

    @classmethod
    def _normalize_singleton_value(mcs, value: object) -> object:
        if isinstance(value, dict):
            return tuple(sorted((str(key), mcs._normalize_singleton_value(item)) for key, item in value.items()))
        if isinstance(value, (list, tuple)):
            return tuple(mcs._normalize_singleton_value(item) for item in value)
        if isinstance(value, set):
            return tuple(sorted(mcs._normalize_singleton_value(item) for item in value))
        try:
            hash(value)
            return value
        except TypeError:
            return (type(value), id(value))


class BaseLLM(ABC, metaclass=SingletonABCMeta):
    """Represents the base l l m component."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError

    @abstractmethod
    def structured_generate(self, prompt: str, schema: type, **kwargs: Any) -> Any:
        raise NotImplementedError
