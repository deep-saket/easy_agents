from dataclasses import dataclass
from pathlib import Path

from mailmind.LLM.huggingface import HuggingFaceLLM
from mailmind.classifiers.llm import OptionalLLMClassifierAdapter
from mailmind.classifiers.rules import RulesBasedClassifier
from mailmind.core.models import Category, EmailMessage, SuggestedAction
from mailmind.core.policies import YAMLPolicyProvider


@dataclass(slots=True)
class FakeLocalLLM(HuggingFaceLLM):
    model_name: str = "fake/model"

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        return {
            "priority_score": 0.88,
            "category": "deep_tech_opportunity",
            "confidence": 0.84,
            "reason_codes": ["llm_startup_signal", "founding_role"],
            "suggested_action": "notify_and_draft",
            "summary": "LLM marked this as a strong deep-tech opportunity.",
        }


def test_llm_classifier_uses_local_model_when_enabled() -> None:
    classifier = OptionalLLMClassifierAdapter(
        fallback=RulesBasedClassifier(YAMLPolicyProvider(Path("policies/default_policy.yaml"))),
        llm=FakeLocalLLM(),
        enabled=True,
    )
    message = EmailMessage(
        source_id="local-llm-1",
        from_email="builder@frontierstartups.ai",
        subject="Founding engineer role for applied AI systems",
        body_text="We are looking for a founding engineer to build deep-tech products with strong upside.",
        received_at="2026-03-29T08:00:00+00:00",
    )
    result = classifier.classify(message)
    assert result.category == Category.DEEP_TECH_OPPORTUNITY
    assert result.suggested_action == SuggestedAction.NOTIFY_AND_DRAFT
    assert result.priority_score == 0.88
