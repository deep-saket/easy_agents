from __future__ import annotations

from dataclasses import dataclass

from mailmind.core.interfaces import MessageRepository
from mailmind.core.models import ToolExecutionLog
from mailmind.schemas.tools import ToolCall, ToolExecutionResult
from tools.registry import ToolRegistry


@dataclass(slots=True)
class ToolExecutor:
    registry: ToolRegistry
    repository: MessageRepository

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
            return ToolExecutionResult(
                tool_name=tool_name,
                status="completed",
                output=validated_output.model_dump(mode="json"),
            ).model_dump(mode="json")
        except Exception as exc:
            log.status = "failed"
            log.error = str(exc)
            self.repository.save_tool_log(log)
            raise

    def execute_call(self, call: ToolCall) -> dict:
        return self.execute(call.tool_name, call.arguments)
