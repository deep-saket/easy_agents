from __future__ import annotations

from dataclasses import dataclass

from mailmind.core.interfaces import MessageClassifier
from mailmind.core.models import ClassificationResult, EmailMessage


@dataclass(slots=True)
class OptionalLLMClassifierAdapter(MessageClassifier):
    fallback: MessageClassifier
    enabled: bool = False

    def classify(self, message: EmailMessage) -> ClassificationResult:
        if not self.enabled:
            return self.fallback.classify(message)
        # TODO: Replace this stub with a real model/provider call guarded by privacy controls.
        result = self.fallback.classify(message)
        result.reason_codes.append("llm_adapter_stubbed")
        return result

