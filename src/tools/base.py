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
    """Defines the contract every reusable platform tool must satisfy.

    A tool is the smallest executable capability the agent platform exposes.
    Agents should not directly embed domain actions such as searching email,
    writing memory, or drafting a reply. Instead, they invoke tools through the
    registry and executor so that:

    - inputs are schema-validated
    - outputs are schema-validated
    - calls are observable and auditable
    - capabilities remain reusable across agents

    Concrete tools declare metadata plus strict Pydantic schemas, then provide
    one `execute` implementation for the actual capability.
    """

    name: str
    description: str
    input_schema: type[InputT]
    output_schema: type[OutputT]

    @abstractmethod
    def execute(self, input: InputT) -> OutputT:
        """Runs the tool with validated structured input.

        Args:
            input: A Pydantic model already validated against `input_schema`.

        Returns:
            A Pydantic model instance matching `output_schema`.
        """
        raise NotImplementedError
