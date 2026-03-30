from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from mailmind.schemas.emails import EmailDetail, EmailSummary


class ToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolPlan(BaseModel):
    steps: list[ToolCall] = Field(default_factory=list)


class ToolExecutionResult(BaseModel):
    tool_name: str
    status: str
    output: dict[str, Any]


class AgentRunResult(BaseModel):
    plan: ToolPlan
    results: list[ToolExecutionResult] = Field(default_factory=list)


class GmailFetchInput(BaseModel):
    process_messages: bool = True


class GmailFetchOutput(BaseModel):
    fetched_count: int
    processed_count: int
    emails: list[EmailSummary] = Field(default_factory=list)


class EmailClassifierInput(BaseModel):
    message_ids: list[str] = Field(default_factory=list)


class EmailClassifierOutput(BaseModel):
    classified_count: int
    emails: list[EmailSummary] = Field(default_factory=list)


class EmailSearchInput(BaseModel):
    query: str | None = None
    category: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    sender: str | None = None
    only_important: bool = False
    limit: int = 50


class EmailSearchOutput(BaseModel):
    emails: list[EmailSummary] = Field(default_factory=list)


class DraftReplyInput(BaseModel):
    message_id: str


class DraftReplyOutput(BaseModel):
    draft_id: str
    message_id: str
    subject: str
    body_text: str


class NotificationInput(BaseModel):
    approval_id: str | None = None
    message_id: str | None = None
    enqueue_only: bool = True


class NotificationOutput(BaseModel):
    status: str
    approval_id: str | None = None
    message_id: str | None = None


class EmailSummaryInput(BaseModel):
    message_ids: list[str] = Field(default_factory=list)
    max_items: int = 5


class EmailSummaryOutput(BaseModel):
    summaries: list[EmailDetail] = Field(default_factory=list)
    combined_summary: str
