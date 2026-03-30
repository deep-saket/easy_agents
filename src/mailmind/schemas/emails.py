from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EmailSummary(BaseModel):
    id: str
    source_id: str
    from_email: str
    from_name: str | None = None
    subject: str
    received_at: datetime
    category: str | None = None
    priority_score: float | None = None
    summary: str | None = None


class EmailDetail(BaseModel):
    summary: EmailSummary
    body_text: str
    labels: list[str] = Field(default_factory=list)

