"""Hybrid callback-time extraction for privacy-safe callback flows."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from agents.collection_agent.llm_structured import StructuredOutputRunner


class _CallbackTimePayload(BaseModel):
    callback_time: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_clarification: bool = False


def extract_callback_time(text: str, *, llm: Any | None = None) -> str:
    deterministic = _extract_deterministic(text)
    if deterministic:
        return deterministic
    if llm is None:
        return ""

    source = re.sub(r"\s+", " ", str(text or "").strip())
    if not source:
        return ""
    try:
        payload = StructuredOutputRunner(llm, max_retries=1).run(
            system_prompt=(
                "Extract only the callback timing explicitly stated by the speaker. "
                "Never infer or invent a date, time, timezone, or AM/PM value. "
                "Return an empty callback_time and needs_clarification=true when the timing is vague."
            ),
            user_prompt=(
                "Return JSON with callback_time, confidence, and needs_clarification. "
                "Use a short natural phrase suitable after 'I will call them', such as "
                "'at 5:30 PM today' or 'tomorrow morning'.\n"
                f"Customer message: {source}"
            ),
            schema=_CallbackTimePayload,
        )
    except Exception:
        return ""

    candidate = re.sub(r"\s+", " ", payload.callback_time.strip())
    if payload.needs_clarification or payload.confidence < 0.75:
        return ""
    return candidate if _is_grounded(candidate=candidate, source=source) else ""


def _extract_deterministic(text: str) -> str:
    source = re.sub(r"\s+", " ", str(text or "").strip())
    lowered = source.lower()
    lowered = re.sub(r"\b(?:tommarrow|tommorow|tommorrow)\b", "tomorrow", lowered)
    if not lowered:
        return ""

    time_match = re.search(
        r"\b(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b",
        lowered,
    )
    day = _extract_day(lowered)
    if time_match:
        hour = int(time_match.group(1))
        minute = time_match.group(2)
        meridiem = "AM" if time_match.group(3).startswith("a") else "PM"
        clock = f"{hour}:{minute} {meridiem}" if minute else f"{hour} {meridiem}"
        return f"at {clock}{f' {day}' if day else ''}"

    inferred_period = ""
    if "morning" in lowered:
        inferred_period = "AM"
    elif any(term in lowered for term in ("afternoon", "evening", "tonight", "night")):
        inferred_period = "PM"
    if inferred_period:
        bare_time_match = re.search(r"\b(?:at\s*)?(\d{1,2})(?::(\d{2}))?\b", lowered)
        if bare_time_match:
            hour = int(bare_time_match.group(1))
            minute = bare_time_match.group(2)
            clock = f"{hour}:{minute} {inferred_period}" if minute else f"{hour} {inferred_period}"
            return f"at {clock}{f' {day}' if day else ''}"

    period_patterns = (
        (r"\bthis\s+(morning|afternoon|evening|night)\b", "this {0}"),
        (r"\b(tomorrow)\s+(morning|afternoon|evening|night)\b", "{0} {1}"),
        (r"\b(today)\s+(morning|afternoon|evening|night)\b", "{0} {1}"),
        (r"\b(next\s+week)\b", "{0}"),
        (r"\b(after|before)\s+(lunch|dinner|work)\b", "{0} {1}"),
    )
    for pattern, template in period_patterns:
        match = re.search(pattern, lowered)
        if match:
            return template.format(*match.groups())

    if day and day not in {"today", "tomorrow"}:
        return day
    return ""


def _extract_day(lowered: str) -> str:
    for term in (
        "today",
        "tomorrow",
        "next monday",
        "next tuesday",
        "next wednesday",
        "next thursday",
        "next friday",
        "next saturday",
        "next sunday",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ):
        if re.search(rf"\b{re.escape(term)}\b", lowered):
            return term
    return ""


def _is_grounded(*, candidate: str, source: str) -> bool:
    if not candidate:
        return False
    candidate_lower = candidate.lower()
    source_lower = source.lower()
    if candidate_lower in {"later", "sometime", "sometime later", "whenever", "anytime"}:
        return False

    if set(re.findall(r"\d+", candidate_lower)) - set(re.findall(r"\d+", source_lower)):
        return False
    temporal_terms = {
        "today",
        "tomorrow",
        "morning",
        "afternoon",
        "evening",
        "night",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "lunch",
        "dinner",
    }
    used_terms = {term for term in temporal_terms if term in candidate_lower}
    if not all(term in source_lower for term in used_terms):
        return False

    ignored = {"at", "on", "in", "the", "this", "next", "around", "after", "before"}
    candidate_tokens = {
        token for token in re.findall(r"[a-z]+", candidate_lower) if token not in ignored
    }
    source_tokens = set(re.findall(r"[a-z]+", source_lower))
    return bool(candidate_tokens) and candidate_tokens.issubset(source_tokens)


__all__ = ["extract_callback_time"]
