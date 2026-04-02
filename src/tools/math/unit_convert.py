"""Created: 2026-04-02

Purpose: Implements a small unit conversion tool for simple agents.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.tools.base import BaseTool


class UnitConvertInput(BaseModel):
    """Defines the validated input for unit conversion."""

    value: float = Field(description="Numeric value to convert.")
    from_unit: str = Field(description="Original unit, for example mile or celsius.")
    to_unit: str = Field(description="Target unit, for example km or fahrenheit.")


class UnitConvertOutput(BaseModel):
    """Defines the validated output for unit conversion."""

    original_value: float
    from_unit: str
    to_unit: str
    converted_value: float


class UnitConvertTool(BaseTool[UnitConvertInput, UnitConvertOutput]):
    """Converts values across a small set of common units.

    The tool intentionally supports a compact, explicit unit list so it stays
    reliable as a demo/framework example rather than trying to be a full
    scientific conversion engine.
    """

    name = "unit_convert"
    description = "Convert a numeric value between common length, weight, and temperature units."
    input_schema = UnitConvertInput
    output_schema = UnitConvertOutput

    _length_to_meter = {
        "m": 1.0,
        "meter": 1.0,
        "meters": 1.0,
        "km": 1000.0,
        "kilometer": 1000.0,
        "kilometers": 1000.0,
        "mile": 1609.344,
        "miles": 1609.344,
        "mi": 1609.344,
        "ft": 0.3048,
        "foot": 0.3048,
        "feet": 0.3048,
    }
    _weight_to_kg = {
        "kg": 1.0,
        "kilogram": 1.0,
        "kilograms": 1.0,
        "g": 0.001,
        "gram": 0.001,
        "grams": 0.001,
        "lb": 0.45359237,
        "lbs": 0.45359237,
        "pound": 0.45359237,
        "pounds": 0.45359237,
    }
    _temperature_units = {"c", "celsius", "f", "fahrenheit", "k", "kelvin"}

    def execute(self, input: UnitConvertInput) -> UnitConvertOutput:
        """Converts the provided value from one unit into another.

        Args:
            input: Structured conversion request with value and units.

        Returns:
            The converted numeric value and the normalized units.
        """
        from_unit = input.from_unit.strip().lower()
        to_unit = input.to_unit.strip().lower()

        if from_unit in self._length_to_meter and to_unit in self._length_to_meter:
            meters = input.value * self._length_to_meter[from_unit]
            converted = meters / self._length_to_meter[to_unit]
        elif from_unit in self._weight_to_kg and to_unit in self._weight_to_kg:
            kilograms = input.value * self._weight_to_kg[from_unit]
            converted = kilograms / self._weight_to_kg[to_unit]
        elif from_unit in self._temperature_units and to_unit in self._temperature_units:
            converted = self._convert_temperature(input.value, from_unit, to_unit)
        else:
            raise ValueError(f"Unsupported conversion: {input.from_unit} -> {input.to_unit}")

        converted = round(converted, 6)
        return UnitConvertOutput(
            original_value=input.value,
            from_unit=from_unit,
            to_unit=to_unit,
            converted_value=converted,
        )

    def _convert_temperature(self, value: float, from_unit: str, to_unit: str) -> float:
        """Converts temperature values by normalizing through Celsius."""
        celsius = self._to_celsius(value, from_unit)
        return self._from_celsius(celsius, to_unit)

    @staticmethod
    def _to_celsius(value: float, unit: str) -> float:
        """Normalizes temperature into Celsius."""
        if unit in {"c", "celsius"}:
            return value
        if unit in {"f", "fahrenheit"}:
            return (value - 32) * 5 / 9
        if unit in {"k", "kelvin"}:
            return value - 273.15
        raise ValueError(f"Unsupported temperature unit: {unit}")

    @staticmethod
    def _from_celsius(value: float, unit: str) -> float:
        """Converts a Celsius value into the target temperature unit."""
        if unit in {"c", "celsius"}:
            return value
        if unit in {"f", "fahrenheit"}:
            return (value * 9 / 5) + 32
        if unit in {"k", "kelvin"}:
            return value + 273.15
        raise ValueError(f"Unsupported temperature unit: {unit}")
