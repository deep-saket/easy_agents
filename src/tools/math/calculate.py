"""Created: 2026-04-02

Purpose: Implements a safe arithmetic calculation tool for simple agents.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

from pydantic import BaseModel, Field

from src.tools.base import BaseTool


class CalculateInput(BaseModel):
    """Defines the validated input for arithmetic evaluation."""

    expression: str = Field(description="Arithmetic expression such as 12 * (3 + 4).")


class CalculateOutput(BaseModel):
    """Defines the validated output for arithmetic evaluation."""

    expression: str
    result: float | int


class CalculateTool(BaseTool[CalculateInput, CalculateOutput]):
    """Safely evaluates a restricted arithmetic expression.

    The tool allows only numeric constants, parentheses, and standard
    arithmetic operators. It intentionally does not execute arbitrary Python.
    """

    name = "calculate"
    description = "Evaluate a basic arithmetic expression."
    input_schema = CalculateInput
    output_schema = CalculateOutput

    _binary_ops: dict[type[ast.AST], Any] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    _unary_ops: dict[type[ast.AST], Any] = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    def execute(self, input: CalculateInput) -> CalculateOutput:
        """Evaluates the arithmetic expression from validated input.

        Args:
            input: Structured arithmetic input containing an expression string.

        Returns:
            The original expression and its numeric result.
        """
        parsed = ast.parse(input.expression, mode="eval")
        result = self._eval_node(parsed.body)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return CalculateOutput(expression=input.expression, result=result)

    def _eval_node(self, node: ast.AST) -> float | int:
        """Recursively evaluates an allowed arithmetic syntax tree."""
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self._binary_ops:
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            return self._binary_ops[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._unary_ops:
            operand = self._eval_node(node.operand)
            return self._unary_ops[type(node.op)](operand)
        raise ValueError("Only basic arithmetic expressions are allowed.")
