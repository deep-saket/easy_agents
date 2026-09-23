"""Central allowlisting, bounding, and secret redaction for trace events."""

from __future__ import annotations

import re
from typing import Any

from easy_agents.observability.contracts import EntityReference, TraceEvent


_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "headers",
    "password",
    "prompt",
    "raw_input",
    "raw_output",
    "request_body",
    "response",
    "secret",
    "state",
    "token",
    "tool_arguments",
    "tool_result",
    "user_input",
    "memory_value",
    "observation",
    "observations",
}

_COMMON_ATTRIBUTE_KEYS = {
    "agent_name",
    "alert_id",
    "approval_id",
    "candidate_count",
    "candidate_ids",
    "call_kind",
    "completion_tokens",
    "effect_count",
    "effects",
    "error_code",
    "error_type",
    "guilds",
    "memory_context_keys",
    "memory_scope",
    "matched_terms",
    "model_id",
    "node_name",
    "objective_length",
    "playbook_id",
    "policy_ids",
    "prompt_tokens",
    "reason_count",
    "result_count",
    "route",
    "source_status",
    "source_event_id",
    "specialist_id",
    "step",
    "step_id",
    "step_kind",
    "team_size",
    "tested_count",
    "passed_count",
    "failed_count",
    "tool_name",
    "total_tokens",
    "warning_count",
    "validation_id",
}

_SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)(?:api[_-]?key|password|secret|token)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{12,}\b"),
)


class EventRedactor:
    """Produces the only event representation allowed into storage or SSE."""

    version = 1

    def __init__(
        self,
        *,
        max_string_length: int = 512,
        max_collection_items: int = 32,
        max_depth: int = 5,
    ) -> None:
        self.max_string_length = max_string_length
        self.max_collection_items = max_collection_items
        self.max_depth = max_depth

    def redact(self, event: TraceEvent) -> TraceEvent:
        """Returns an allowlisted, bounded copy of one event."""

        attributes = {
            key: self._clean(value, depth=0)
            for key, value in event.attributes.items()
            if key in _COMMON_ATTRIBUTE_KEYS and key.lower() not in _SENSITIVE_KEYS
        }
        metrics = {
            str(key)[:64]: value
            for key, value in list(event.metrics.items())[: self.max_collection_items]
            if value is None or isinstance(value, (int, float))
        }
        return event.model_copy(
            update={
                "summary": self._redact_string(event.summary, limit=240),
                "mission_id": self._clean_identifier(event.mission_id),
                "work_order_id": self._clean_identifier(event.work_order_id),
                "run_id": self._clean_identifier(event.run_id),
                "trace_id": self._clean_identifier(event.trace_id),
                "span_id": self._clean_identifier(event.span_id),
                "parent_span_id": self._clean_identifier(event.parent_span_id),
                "actor": self._clean_reference(event.actor),
                "subject": self._clean_reference(event.subject),
                "attributes": attributes,
                "metrics": metrics,
                "redaction_version": self.version,
            }
        )

    def _clean_identifier(self, value: str | None) -> str | None:
        if value is None:
            return None
        return self._redact_string(value, limit=200)

    def _clean_reference(self, value: EntityReference | None) -> EntityReference | None:
        if value is None:
            return None
        return EntityReference(
            kind=self._redact_string(value.kind, limit=64),
            id=self._redact_string(value.id, limit=200),
        )

    def _clean(self, value: Any, *, depth: int) -> Any:
        if depth >= self.max_depth:
            return "[bounded]"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return self._redact_string(value, limit=self.max_string_length)
        if isinstance(value, (list, tuple, set)):
            return [
                self._clean(item, depth=depth + 1)
                for item in list(value)[: self.max_collection_items]
            ]
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for raw_key, item in list(value.items())[: self.max_collection_items]:
                key = str(raw_key)[:64]
                if key.lower() in _SENSITIVE_KEYS:
                    cleaned[key] = "[redacted]"
                else:
                    cleaned[key] = self._clean(item, depth=depth + 1)
            return cleaned
        return self._redact_string(repr(value), limit=self.max_string_length)

    def _redact_string(self, value: str, *, limit: int) -> str:
        cleaned = value.replace("\x00", "")
        for pattern in _SECRET_PATTERNS:
            cleaned = pattern.sub("[redacted]", cleaned)
        if len(cleaned) > limit:
            return f"{cleaned[: max(0, limit - 1)]}…"
        return cleaned
