"""Created: 2026-03-31

Purpose: Implements the common module for the shared schemas platform layer.
"""

from __future__ import annotations

from pydantic import BaseModel


class SessionRef(BaseModel):
    """Represents the session ref component."""
    session_id: str

