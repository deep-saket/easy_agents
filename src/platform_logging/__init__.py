"""Reusable logging helpers with lazy compatibility exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["AuditLogger", "StructuredLogger"]


def __getattr__(name: str) -> Any:
    """Avoids importing storage dependencies when only tracing is needed."""

    module_names = {
        "AuditLogger": ".audit_logger",
        "StructuredLogger": ".structured_logger",
    }
    module_name = module_names.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value
