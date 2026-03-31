from __future__ import annotations

from abc import ABC, abstractmethod


class BaseMemory(ABC):
    @abstractmethod
    def set_state(self, **kwargs: object) -> None:
        raise NotImplementedError

