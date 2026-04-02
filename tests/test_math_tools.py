"""Created: 2026-04-02

Purpose: Tests the reusable math tools used by the math agent notebook.
"""

from src.tools.math import CalculateInput, CalculateTool, UnitConvertInput, UnitConvertTool


def test_calculate_tool_evaluates_basic_expression() -> None:
    """Verifies the calculate tool evaluates arithmetic safely."""
    tool = CalculateTool()

    result = tool.execute(CalculateInput(expression="12 * (3 + 4)"))

    assert result.result == 84


def test_unit_convert_tool_converts_common_units() -> None:
    """Verifies the conversion tool handles a common length conversion."""
    tool = UnitConvertTool()

    result = tool.execute(UnitConvertInput(value=5, from_unit="miles", to_unit="km"))

    assert result.converted_value == 8.04672
