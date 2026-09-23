"""Adapters from existing graph trace dictionaries to canonical events."""

from __future__ import annotations

from typing import Any

from easy_agents.observability.contracts import (
    EntityReference,
    Severity,
    TraceEvent,
)


_EVENT_MAP = {
    "turn_started": "specialist.started",
    "turn_finished": "specialist.completed",
    "node_started": "node.started",
    "node_finished": "node.completed",
    "node_state": "node.state_changed",
    "llm_call": "model.completed",
    "tool_call": "tool.completed",
    "hop_started": "handoff.requested",
    "hop_update": "handoff.completed",
}


def normalize_legacy_event(payload: dict[str, Any]) -> TraceEvent:
    """Converts one existing ``TraceSink`` dictionary into a safe draft."""

    original_type = str(payload.get("event", "trace_event"))
    event_type = _EVENT_MAP.get(original_type, _canonical_name(original_type))
    status = str(payload.get("status")) if payload.get("status") is not None else None
    if status == "failed":
        if event_type.endswith(".completed"):
            event_type = f"{event_type.rsplit('.', 1)[0]}.failed"
        severity = Severity.ERROR
    else:
        severity = Severity.INFO

    agent_name = payload.get("agent_name")
    node_name = payload.get("node_name")
    model_name = payload.get("model_name")
    tool_name = payload.get("tool_name")
    actor = (
        EntityReference(kind="specialist", id=str(agent_name))
        if agent_name
        else None
    )
    subject: EntityReference | None = None
    if node_name:
        subject = EntityReference(kind="node", id=str(node_name))
    elif model_name:
        subject = EntityReference(kind="model", id=_model_id(str(model_name)))
    elif tool_name:
        subject = EntityReference(kind="tool", id=str(tool_name))

    attributes: dict[str, Any] = {}
    for key in (
        "agent_name",
        "node_name",
        "step",
        "model_name",
        "call_kind",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "tool_name",
        "route",
        "memory_context_keys",
    ):
        if payload.get(key) is not None:
            normalized_key = "model_id" if key == "model_name" else key
            attributes[normalized_key] = payload[key]

    state = payload.get("state")
    if isinstance(state, dict):
        if state.get("route") is not None:
            attributes["route"] = state["route"]
        keys = state.get("memory_context_keys")
        if isinstance(keys, list):
            attributes["memory_context_keys"] = keys

    metrics = {
        key: payload.get(key)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if payload.get(key) is None or isinstance(payload.get(key), (int, float))
    }
    summary = _summary(event_type, actor=actor, subject=subject)
    return TraceEvent(
        event_type=event_type,
        severity=severity,
        status=status,
        trace_id=str(payload["trace_id"]) if payload.get("trace_id") else None,
        actor=actor,
        subject=subject,
        summary=summary,
        duration_ms=_duration(payload.get("duration_ms")),
        attributes=attributes,
        metrics=metrics,
    )


def _canonical_name(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if "." in normalized:
        return normalized
    if "_" in normalized:
        area, action = normalized.split("_", 1)
        return f"{area}.{action}"
    return f"trace.{normalized or 'event'}"


def _model_id(value: str) -> str:
    return "mac_gemma" if "gemma" in value.lower() else value


def _summary(
    event_type: str,
    *,
    actor: EntityReference | None,
    subject: EntityReference | None,
) -> str:
    entity = subject or actor
    label = entity.id if entity is not None else "runtime"
    return f"{event_type.replace('.', ' ')}: {label}"


def _duration(value: Any) -> float | None:
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    return None
