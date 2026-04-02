"""Created: 2026-04-02

Purpose: Implements execution tracing for shared agent graphs, nodes, tools,
and llm calls.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Iterator
from uuid import uuid4


def _utc_now() -> datetime:
    """Returns the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


@dataclass(slots=True)
class LLMCallTrace:
    """Captures one llm invocation inside an agent turn."""

    call_id: str
    node_name: str | None
    model_name: str
    call_kind: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    started_at: datetime
    finished_at: datetime
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Serializes the llm trace into a JSON-friendly payload."""
        return {
            "call_id": self.call_id,
            "node_name": self.node_name,
            "model_name": self.model_name,
            "call_kind": self.call_kind,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_ms": self.duration_ms,
        }


@dataclass(slots=True)
class ToolCallTrace:
    """Captures one tool execution inside an agent turn."""

    tool_name: str
    node_name: str | None
    status: str
    started_at: datetime
    finished_at: datetime
    duration_ms: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes the tool trace into a JSON-friendly payload."""
        return {
            "tool_name": self.tool_name,
            "node_name": self.node_name,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


@dataclass(slots=True)
class NodeTrace:
    """Captures one graph node execution inside an agent turn."""

    node_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: float | None = None
    error: str | None = None

    def finish(self, *, status: str, error: str | None = None) -> None:
        """Marks the node trace as finished."""
        finished_at = _utc_now()
        self.finished_at = finished_at
        self.duration_ms = round((finished_at - self.started_at).total_seconds() * 1000, 3)
        self.status = status
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        """Serializes the node trace into a JSON-friendly payload."""
        return {
            "node_name": self.node_name,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


@dataclass(slots=True)
class ExecutionTrace:
    """Aggregates one full agent turn trace.

    The trace is intentionally generic so any graph-based agent can use it to
    answer questions such as:

    - which nodes ran and in what order
    - which tools were called
    - which llms were invoked
    - how many tokens were consumed
    - how long the turn took
    """

    agent_name: str
    session_id: str
    user_input: str
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: datetime = field(default_factory=_utc_now)
    finished_at: datetime | None = None
    status: str = "running"
    node_traces: list[NodeTrace] = field(default_factory=list)
    llm_calls: list[LLMCallTrace] = field(default_factory=list)
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    error: str | None = None

    def start_node(self, node_name: str) -> NodeTrace:
        """Creates and registers a node trace entry."""
        trace = NodeTrace(node_name=node_name, status="running", started_at=_utc_now())
        self.node_traces.append(trace)
        return trace

    def add_llm_call(
        self,
        *,
        model_name: str,
        call_kind: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
        duration_ms: float,
        node_name: str | None = None,
    ) -> None:
        """Adds one llm call record to the trace."""
        finished_at = _utc_now()
        started_at = finished_at
        self.llm_calls.append(
            LLMCallTrace(
                call_id=str(uuid4()),
                node_name=node_name,
                model_name=model_name,
                call_kind=call_kind,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
            )
        )

    def add_tool_call(
        self,
        *,
        tool_name: str,
        status: str,
        duration_ms: float,
        error: str | None = None,
        node_name: str | None = None,
    ) -> None:
        """Adds one tool execution record to the trace."""
        finished_at = _utc_now()
        started_at = finished_at
        self.tool_calls.append(
            ToolCallTrace(
                tool_name=tool_name,
                node_name=node_name,
                status=status,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                error=error,
            )
        )

    def finish(self, *, status: str, error: str | None = None) -> None:
        """Marks the full agent turn trace as completed or failed."""
        self.finished_at = _utc_now()
        self.status = status
        self.error = error

    def summary(self) -> dict[str, Any]:
        """Returns a compact execution summary."""
        prompt_tokens = sum(call.prompt_tokens or 0 for call in self.llm_calls)
        completion_tokens = sum(call.completion_tokens or 0 for call in self.llm_calls)
        total_tokens = sum(call.total_tokens or 0 for call in self.llm_calls)
        models = sorted({call.model_name for call in self.llm_calls})
        return {
            "trace_id": self.trace_id,
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "status": self.status,
            "node_hits": [trace.node_name for trace in self.node_traces],
            "node_count": len(self.node_traces),
            "llm_call_count": len(self.llm_calls),
            "tool_call_count": len(self.tool_calls),
            "models": models,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "error": self.error,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serializes the full execution trace."""
        return {
            "trace_id": self.trace_id,
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "user_input": self.user_input,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error,
            "summary": self.summary(),
            "nodes": [trace.to_dict() for trace in self.node_traces],
            "llm_calls": [call.to_dict() for call in self.llm_calls],
            "tool_calls": [call.to_dict() for call in self.tool_calls],
        }


_active_trace: ContextVar[ExecutionTrace | None] = ContextVar("active_execution_trace", default=None)
_active_node_name: ContextVar[str | None] = ContextVar("active_node_name", default=None)


@contextmanager
def trace_turn(trace: ExecutionTrace) -> Iterator[ExecutionTrace]:
    """Sets the active agent-turn trace for nested node/tool/llm events."""
    token = _active_trace.set(trace)
    try:
        yield trace
    finally:
        _active_trace.reset(token)


@contextmanager
def trace_node(node_name: str) -> Iterator[NodeTrace | None]:
    """Sets the active node name and records one node execution span."""
    trace = current_trace()
    node_trace = trace.start_node(node_name) if trace is not None else None
    token = _active_node_name.set(node_name)
    try:
        yield node_trace
        if node_trace is not None:
            node_trace.finish(status="completed")
    except Exception as exc:
        if node_trace is not None:
            node_trace.finish(status="failed", error=str(exc))
        raise
    finally:
        _active_node_name.reset(token)


def current_trace() -> ExecutionTrace | None:
    """Returns the active execution trace when a turn is being traced."""
    return _active_trace.get()


def current_node_name() -> str | None:
    """Returns the active node name when code is running inside a node span."""
    return _active_node_name.get()


def record_llm_call(
    *,
    model_name: str,
    call_kind: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    duration_ms: float,
) -> None:
    """Appends an llm call to the active trace when tracing is enabled."""
    trace = current_trace()
    if trace is None:
        return
    trace.add_llm_call(
        model_name=model_name,
        call_kind=call_kind,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        duration_ms=duration_ms,
        node_name=current_node_name(),
    )


def record_tool_call(
    *,
    tool_name: str,
    status: str,
    duration_ms: float,
    error: str | None = None,
) -> None:
    """Appends a tool execution to the active trace when tracing is enabled."""
    trace = current_trace()
    if trace is None:
        return
    trace.add_tool_call(
        tool_name=tool_name,
        status=status,
        duration_ms=duration_ms,
        error=error,
        node_name=current_node_name(),
    )


@contextmanager
def measure_duration() -> Iterator[callable]:
    """Measures wall-clock duration for llm and tool calls."""
    started = perf_counter()

    def elapsed_ms() -> float:
        return round((perf_counter() - started) * 1000, 3)

    yield elapsed_ms
