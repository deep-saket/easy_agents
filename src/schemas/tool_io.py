"""Created: 2026-03-31

Purpose: Implements the tool io module for the shared schemas platform layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.memory.models import MemoryRecord
from src.schemas.emails import EmailDetail, EmailSummary


class ToolCall(BaseModel):
    """Represents one tool invocation request."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolPlan(BaseModel):
    """Represents an ordered list of tool calls."""

    steps: list[ToolCall] = Field(default_factory=list)


class ToolExecutionResult(BaseModel):
    """Represents the result of a tool invocation."""

    tool_name: str
    status: str
    output: dict[str, Any]


class AgentRunResult(BaseModel):
    """Represents the result of one agent run."""

    plan: ToolPlan
    results: list[ToolExecutionResult] = Field(default_factory=list)


class PlannerDecision(BaseModel):
    """Represents a planner decision for one graph step."""

    thought: str
    tool_call: ToolCall | None = None
    respond_directly: bool = False
    response_text: str | None = None
    done: bool = False


class GmailFetchInput(BaseModel):
    """Represents input for Gmail fetch operations."""

    process_messages: bool = True


class GmailFetchOutput(BaseModel):
    """Represents output for Gmail fetch operations."""

    fetched_count: int
    processed_count: int
    emails: list[EmailSummary] = Field(default_factory=list)


class EmailClassifierInput(BaseModel):
    """Represents input for email classification operations."""

    message_ids: list[str] = Field(default_factory=list)


class EmailClassifierOutput(BaseModel):
    """Represents output for email classification operations."""

    classified_count: int
    emails: list[EmailSummary] = Field(default_factory=list)


class EmailSearchInput(BaseModel):
    """Represents input for email search operations."""

    query: str | None = None
    category: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    sender: str | None = None
    only_important: bool = False
    limit: int = 50


class EmailSearchOutput(BaseModel):
    """Represents output for email search operations."""

    total: int = 0
    categories: dict[str, int] = Field(default_factory=dict)
    emails: list[EmailSummary] = Field(default_factory=list)


class DraftReplyInput(BaseModel):
    """Represents input for reply-draft generation."""

    message_id: str


class DraftReplyOutput(BaseModel):
    """Represents output for reply-draft generation."""

    draft_id: str
    message_id: str
    subject: str
    body_text: str


class EmailSendInput(BaseModel):
    """Represents input for sending a stored email draft or explicit reply."""

    message_id: str
    recipients: list[str] = Field(default_factory=list)
    subject: str | None = None
    body_text: str | None = None


class EmailSendOutput(BaseModel):
    """Represents output for email send operations."""

    status: str
    message_id: str
    draft_id: str | None = None
    provider_message_id: str | None = None
    thread_id: str | None = None
    recipients: list[str] = Field(default_factory=list)
    subject: str


class NotificationInput(BaseModel):
    """Represents input for notification execution."""

    approval_id: str | None = None
    message_id: str | None = None
    enqueue_only: bool = True


class NotificationOutput(BaseModel):
    """Represents output for notification execution."""

    status: str
    approval_id: str | None = None
    message_id: str | None = None


class EmailSummaryInput(BaseModel):
    """Represents input for summarizing stored emails."""

    message_ids: list[str] = Field(default_factory=list)
    max_items: int = 5


class EmailSummaryOutput(BaseModel):
    """Represents output for summarizing stored emails."""

    total: int
    categories: dict[str, int] = Field(default_factory=dict)
    summaries: list[EmailDetail] = Field(default_factory=list)
    combined_summary: str


class MemorySearchInput(BaseModel):
    """Represents input for memory search operations."""

    query: str = ""
    query_candidates: list[str] = Field(default_factory=list)
    stop_on_first_hit: bool = True
    max_queries: int = 3
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = 20


class MemorySearchAttempt(BaseModel):
    """Represents one query attempt inside a memory-search call."""

    query: str
    result_count: int
    result_ids: list[str] = Field(default_factory=list)


class MemorySearchOutput(BaseModel):
    """Represents output for memory search operations."""

    total: int = 0
    memories: list[MemoryRecord] = Field(default_factory=list)
    selected_query: str | None = None
    attempts: list[MemorySearchAttempt] = Field(default_factory=list)


class MemoryWriteInput(BaseModel):
    """Represents input for memory write operations."""

    item: MemoryRecord


class MemoryWriteOutput(BaseModel):
    """Represents output for memory write operations."""

    item: MemoryRecord


__all__ = [
    "AgentRunResult",
    "DraftReplyInput",
    "DraftReplyOutput",
    "EmailClassifierInput",
    "EmailClassifierOutput",
    "EmailSendInput",
    "EmailSendOutput",
    "EmailSearchInput",
    "EmailSearchOutput",
    "EmailSummaryInput",
    "EmailSummaryOutput",
    "GmailFetchInput",
    "GmailFetchOutput",
    "MemorySearchInput",
    "MemorySearchAttempt",
    "MemorySearchOutput",
    "MemoryWriteInput",
    "MemoryWriteOutput",
    "NotificationInput",
    "NotificationOutput",
    "PlannerDecision",
    "ToolCall",
    "ToolExecutionResult",
    "ToolPlan",
]
