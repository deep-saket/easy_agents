"""Created: 2026-03-30

Purpose: Implements the tools module for the shared mailmind platform layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.memory.models import MemoryRecord
from src.mailmind.schemas.emails import EmailDetail, EmailSummary


class ToolCall(BaseModel):
    """Represents the tool call component."""
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolPlan(BaseModel):
    """Represents the tool plan component."""
    steps: list[ToolCall] = Field(default_factory=list)


class ToolExecutionResult(BaseModel):
    """Represents the result for tool execution operations."""
    tool_name: str
    status: str
    output: dict[str, Any]


class AgentRunResult(BaseModel):
    """Represents the result for agent run operations."""
    plan: ToolPlan
    results: list[ToolExecutionResult] = Field(default_factory=list)


class PlannerDecision(BaseModel):
    """Represents the planner decision component."""
    thought: str
    tool_call: ToolCall | None = None
    respond_directly: bool = False
    response_text: str | None = None
    done: bool = False


class GmailFetchInput(BaseModel):
    """Represents input for gmail fetch operations."""
    process_messages: bool = True


class GmailFetchOutput(BaseModel):
    """Represents output for gmail fetch operations."""
    fetched_count: int
    processed_count: int
    emails: list[EmailSummary] = Field(default_factory=list)


class EmailClassifierInput(BaseModel):
    """Represents input for email classifier operations."""
    message_ids: list[str] = Field(default_factory=list)


class EmailClassifierOutput(BaseModel):
    """Represents output for email classifier operations."""
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
    """Represents input for draft reply operations."""
    message_id: str


class DraftReplyOutput(BaseModel):
    """Represents output for draft reply operations."""
    draft_id: str
    message_id: str
    subject: str
    body_text: str


class NotificationInput(BaseModel):
    """Represents input for notification operations."""
    approval_id: str | None = None
    message_id: str | None = None
    enqueue_only: bool = True


class NotificationOutput(BaseModel):
    """Represents output for notification operations."""
    status: str
    approval_id: str | None = None
    message_id: str | None = None


class EmailSummaryInput(BaseModel):
    """Represents input for email summary operations."""
    message_ids: list[str] = Field(default_factory=list)
    max_items: int = 5


class EmailSummaryOutput(BaseModel):
    """Represents output for email summary operations."""
    total: int
    categories: dict[str, int] = Field(default_factory=dict)
    summaries: list[EmailDetail] = Field(default_factory=list)
    combined_summary: str


class MemorySearchInput(BaseModel):
    """Represents input for memory search operations."""
    query: str = ""
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = 20


class MemorySearchOutput(BaseModel):
    """Represents output for memory search operations."""
    total: int = 0
    memories: list[MemoryRecord] = Field(default_factory=list)


class MemoryWriteInput(BaseModel):
    """Represents input for memory write operations."""
    item: MemoryRecord


class MemoryWriteOutput(BaseModel):
    """Represents output for memory write operations."""
    item: MemoryRecord
