"""Created: 2026-03-31

Purpose: Compatibility aliases loaded automatically on interpreter startup.
"""


from __future__ import annotations

import importlib
import sys


def _alias_package(alias: str, target: str) -> None:
    if alias in sys.modules:
        return
    module = importlib.import_module(target)
    sys.modules[alias] = module


_alias_package("LLM", "llm")
