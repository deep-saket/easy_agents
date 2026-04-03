"""Created: 2026-03-30

Purpose: Implements the executor module for the shared tools platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from src.memory.policies import MemoryPolicy
from src.memory.store import MemoryStore
from src.mailmind.core.interfaces import MessageRepository
from src.mailmind.core.models import ToolExecutionLog
from src.mailmind.schemas.tools import ToolCall, ToolExecutionResult
from src.platform_logging.tracing import record_tool_call
from src.tools.registry import ToolRegistry


class NullToolLogRepository:
    """Provides a no-op tool log sink for lightweight graphs and demos.

    Small examples often want to exercise real tools and the shared executor
    without also setting up a full repository implementation. This null object
    keeps the executor API simple by absorbing tool-log writes when durable
    persistence is not needed.
    """

    def save_tool_log(self, log: ToolExecutionLog) -> None:
        """Ignores the tool log while preserving the executor contract.

        Args:
            log: The structured tool execution log that would otherwise be
                persisted.
        """
        del log


@dataclass(slots=True)
class ToolExecutor:
    """Validates, executes, logs, and memory-records tool invocations.

    The executor is the operational layer between planning and capability
    execution.

    A planner decides *which* tool to call and with *what* arguments.
    The registry tells us *which tool object* corresponds to that name.
    The executor then performs the runtime work:

    1. validate input against the tool schema
    2. call the concrete tool implementation
    3. validate the output against the output schema
    4. persist a tool log for observability
    5. optionally write episodic or error memory about the call

    This separation keeps planners free of execution details and keeps tools
    free of logging/audit boilerplate.
    """

    registry: ToolRegistry
    repository: MessageRepository | NullToolLogRepository | None = None
    memory_store: MemoryStore | None = None
    memory_policy: MemoryPolicy | None = None

    def execute(self, tool_name: str, input: dict) -> dict:
        """Executes one tool by name with structured validation and logging.

        Args:
            tool_name: The registered tool name chosen by the planner or agent.
            input: Raw argument payload, typically produced by a planner or
                caller before schema validation.

        Returns:
            A JSON-serializable execution result containing the tool name,
            status, and validated output payload.

        Raises:
            Exception: Re-raises any tool execution error after logging and
                optional error-memory capture.
        """
        tool = self.registry.get(tool_name)
        repository = self.repository or NullToolLogRepository()
        log = ToolExecutionLog(tool_name=tool_name, input_payload=input, status="started")
        started = perf_counter()
        try:
            validated_input = tool.input_schema.model_validate(input)
            output = tool.execute(validated_input)
            validated_output = tool.output_schema.model_validate(output)
            log.status = "completed"
            log.output_payload = validated_output.model_dump(mode="json")
            repository.save_tool_log(log)
            self._write_memory(
                {
                    "event_type": "tool_execution",
                    "agent": "platform",
                    "content": {
                        "tool_name": tool_name,
                        "input": validated_input.model_dump(mode="json"),
                        "output": validated_output.model_dump(mode="json"),
                    },
                    "metadata": {
                        "agent": "platform",
                        "tool_name": tool_name,
                        "status": "completed",
                        "tags": [tool_name, "tool_execution"],
                        "source": "tool",
                        "priority": "low",
                    },
                }
            )
            record_tool_call(
                tool_name=tool_name,
                status="completed",
                duration_ms=round((perf_counter() - started) * 1000, 3),
            )
            return ToolExecutionResult(
                tool_name=tool_name,
                status="completed",
                output=validated_output.model_dump(mode="json"),
            ).model_dump(mode="json")
        except Exception as exc:
            log.status = "failed"
            log.error = str(exc)
            repository.save_tool_log(log)
            self._write_memory(
                {
                    "event_type": "tool_failure",
                    "agent": "platform",
                    "input": input,
                    "output": None,
                    "error": str(exc),
                    "metadata": {
                        "agent": "platform",
                        "tool_name": tool_name,
                        "status": "failed",
                        "tags": [tool_name, "tool_failure"],
                        "source": "tool",
                        "priority": "high",
                    },
                }
            )
            record_tool_call(
                tool_name=tool_name,
                status="failed",
                duration_ms=round((perf_counter() - started) * 1000, 3),
                error=str(exc),
            )
            raise

    def execute_call(self, call: ToolCall) -> dict:
        """Executes a pre-structured `ToolCall` model.

        Args:
            call: A structured tool call containing the name and arguments.

        Returns:
            The same result shape as `execute`.
        """
        return self.execute(call.tool_name, call.arguments)

    def _write_memory(self, event: dict) -> None:
        """Writes a long-term memory event when memory support is configured.

        Args:
            event: A normalized event payload produced around tool execution.
        """
        if self.memory_store is None or self.memory_policy is None:
            return
        if not self.memory_policy.should_store(event):
            return
        self.memory_store.add(self.memory_policy.build_item(event))
