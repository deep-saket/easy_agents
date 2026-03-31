"""Created: 2026-03-30

Purpose: Implements the base module for the shared tools platform layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel


InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class BaseTool(ABC, Generic[InputT, OutputT]):
    name: str
    description: str
    input_schema: type[InputT]
    output_schema: type[OutputT]

    @abstractmethod
    def execute(self, input: InputT) -> OutputT:
        raise NotImplementedError

