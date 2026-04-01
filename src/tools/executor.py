"""Created: 2026-03-30

Purpose: Implements the executor module for the shared tools platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.policies import MemoryPolicy
from src.memory.store import MemoryStore
from src.mailmind.core.interfaces import MessageRepository
from src.mailmind.core.models import ToolExecutionLog
from src.mailmind.schemas.tools import ToolCall, ToolExecutionResult
from src.tools.registry import ToolRegistry


@dataclass(slots=True)
class ToolExecutor:
    registry: ToolRegistry
    repository: MessageRepository
    memory_store: MemoryStore | None = None
    memory_policy: MemoryPolicy | None = None

    def execute(self, tool_name: str, input: dict) -> dict:
        tool = self.registry.get(tool_name)
        log = ToolExecutionLog(tool_name=tool_name, input_payload=input, status="started")
        try:
            validated_input = tool.input_schema.model_validate(input)
            output = tool.execute(validated_input)
            validated_output = tool.output_schema.model_validate(output)
            log.status = "completed"
            log.output_payload = validated_output.model_dump(mode="json")
            self.repository.save_tool_log(log)
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
            return ToolExecutionResult(
                tool_name=tool_name,
                status="completed",
                output=validated_output.model_dump(mode="json"),
            ).model_dump(mode="json")
        except Exception as exc:
            log.status = "failed"
            log.error = str(exc)
            self.repository.save_tool_log(log)
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
            raise

    def execute_call(self, call: ToolCall) -> dict:
        return self.execute(call.tool_name, call.arguments)

    def _write_memory(self, event: dict) -> None:
        if self.memory_store is None or self.memory_policy is None:
            return
        if not self.memory_policy.should_store(event):
            return
        self.memory_store.add(self.memory_policy.build_item(event))
