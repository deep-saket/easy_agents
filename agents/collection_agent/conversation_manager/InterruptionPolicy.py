"""Conversation-manager interruption classification and replay policy."""

from __future__ import annotations

import re


class InterruptionPolicy:
    """Decides whether a new input should replay or supersede active work."""

    _REPEAT_PATTERNS = (
        re.compile(r"\b(can you )?repeat( that| it)?\b", re.IGNORECASE),
        re.compile(r"\bwhat did you say\b", re.IGNORECASE),
        re.compile(r"\bi missed that\b", re.IGNORECASE),
        re.compile(r"\bsay that again\b", re.IGNORECASE),
        re.compile(r"\bcould you say that again\b", re.IGNORECASE),
    )

    def is_repeat_request(self, text: str) -> bool:
        candidate = text.strip()
        if not candidate:
            return False
        return any(pattern.search(candidate) for pattern in self._REPEAT_PATTERNS)

    def classify_text_input(self, text: str) -> str:
        if self.is_repeat_request(text):
            return "repeat_request"
        return "new_information"

    def should_replay(self, text: str) -> bool:
        return self.is_repeat_request(text)
