"""Created: 2026-03-31

Purpose: Implements the ids module for the shared utils platform layer.
"""

from __future__ import annotations

from uuid import uuid4


def new_id() -> str:
    return str(uuid4())

