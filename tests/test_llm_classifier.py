"""Created: 2026-04-05

Purpose: Tests the shared prompt-driven LLM classifier template and the
MailMind-specific email classifier built on top of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from agents.mailmind.helpers import MailMindEmailClassifier
from src.helpers import GenericMultiLabelClassificationOutput, LLMClassifierTemplate
from src.schemas.domain import ActionType, Category, EmailMessage, SuggestedAction


class DemoClassification(BaseModel):
    """Represents a generic structured classifier result."""

    label: str
    reason: str
    confidence: float
    class_probabilities: dict[str, float] | None = None


@dataclass(slots=True)
class FakeStructuredLLM:
    """Records classifier prompts and returns a predefined structured payload."""

    payload: dict[str, object]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def structured_generate(self, prompt: str, schema: type[BaseModel], **kwargs: object) -> BaseModel:
        self.calls.append((str(kwargs.get("system_prompt", "")), prompt))
        return schema.model_validate(self.payload)


def test_llm_classifier_template_renders_json_context() -> None:
    llm = FakeStructuredLLM(
        payload={
            "label": "job",
            "reason": "The message clearly describes a role.",
            "confidence": 0.91,
        }
    )
    classifier = LLMClassifierTemplate(
        llm=llm,
        system_prompt="System classes:\n{classification_classes_json}\nDetails:\n{class_details_json}",
        user_prompt="Input:\n{input_json}",
        classification_classes=["job", "event"],
        class_details={"job": {"description": "Career opportunity"}},
        output_schema=DemoClassification,
    )

    result = classifier.classify({"subject": "Research Engineer opening", "sender": "talent@example.com"})

    assert result.label == "job"
    system_prompt, user_prompt = llm.calls[0]
    assert '"job"' in system_prompt
    assert '"description": "Career opportunity"' in system_prompt
    assert '"subject": "Research Engineer opening"' in user_prompt


def test_llm_classifier_template_supports_multi_label_mode() -> None:
    llm = FakeStructuredLLM(
        payload={
            "labels": ["job", "networking"],
            "reason": "The message is both an opportunity and a warm intro.",
            "confidence": 0.86,
        }
    )
    classifier = LLMClassifierTemplate(
        llm=llm,
        system_prompt="Mode: {classification_mode}\nClasses:\n{classification_classes_json}",
        user_prompt="Input:\n{input_json}",
        classification_classes=["job", "networking", "event"],
        class_details={"job": {"description": "Career opportunity"}},
        output_schema=GenericMultiLabelClassificationOutput,
        multi_label=True,
    )

    result = classifier.classify({"subject": "Founding role and meetup invite"})

    assert result.labels == ["job", "networking"]
    system_prompt, user_prompt = llm.calls[0]
    assert "multi_label" in system_prompt
    assert "Return all applicable classes in a `labels` array." in user_prompt


def test_llm_classifier_template_supports_probability_output() -> None:
    llm = FakeStructuredLLM(
        payload={
            "label": "job",
            "reason": "The message is a strong role fit.",
            "confidence": 0.9,
            "class_probabilities": {
                "job": 0.93,
                "event": 0.12,
            },
        }
    )
    classifier = LLMClassifierTemplate(
        llm=llm,
        system_prompt="Mode: {classification_mode} | calc_prob={calc_prob}",
        user_prompt="Input:\n{input_json}",
        classification_classes=["job", "event"],
        class_details={"job": {"description": "Career opportunity"}},
        output_schema=DemoClassification,
        calc_prob=True,
    )

    result = classifier.classify({"subject": "Research Engineer opening"})

    assert result.class_probabilities == {"job": 0.93, "event": 0.12}
    system_prompt, user_prompt = llm.calls[0]
    assert "calc_prob=True" in system_prompt
    assert "Return `class_probabilities` as independent probabilities for the classified classes." in user_prompt


def test_mailmind_email_classifier_maps_llm_output_to_framework_result() -> None:
    llm = FakeStructuredLLM(
        payload={
            "category": "strong_ml_research_job",
            "requires_action": True,
            "action_type": "reply",
            "impact_score": 0.94,
            "priority_score": 0.89,
            "confidence": 0.87,
            "reason": "Strong-fit research role from a credible sender.",
            "reason_codes": ["research_role", "credible_sender"],
            "suggested_action": "notify_and_draft",
            "summary": "High-value ML research opportunity.",
        }
    )
    classifier = MailMindEmailClassifier(llm=llm)
    message = EmailMessage(
        source_id="gmail-llm-1",
        from_email="talent@frontier.ai",
        subject="Research Engineer, multimodal systems",
        body_text="We are selectively hiring for a frontier multimodal systems role.",
        received_at="2026-04-05T08:00:00+00:00",
    )

    result = classifier.classify(message)

    assert result.category == Category.STRONG_ML_RESEARCH_JOB
    assert result.requires_action is True
    assert result.action_type == ActionType.REPLY
    assert result.suggested_action == SuggestedAction.NOTIFY_AND_DRAFT
    assert result.reasoning == "Strong-fit research role from a credible sender."
    assert result.summary == "High-value ML research opportunity."
    system_prompt, user_prompt = llm.calls[0]
    assert "MailMind's email-classification subroutine" in system_prompt
    assert '"subject": "Research Engineer, multimodal systems"' in user_prompt
