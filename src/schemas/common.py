from __future__ import annotations

from pydantic import BaseModel


class SessionRef(BaseModel):
    session_id: str

