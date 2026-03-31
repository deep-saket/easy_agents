"""Created: 2026-03-30

Purpose: Tests the classifier behavior.
"""

from pathlib import Path

from mailmind.classifiers.rules import RulesBasedClassifier
from mailmind.core.models import Category, EmailMessage, SuggestedAction
from mailmind.core.policies import YAMLPolicyProvider


def test_rules_classifier_marks_research_role_high_priority() -> None:
    classifier = RulesBasedClassifier(YAMLPolicyProvider(Path("policies/default_policy.yaml")))
    message = EmailMessage(
        source_id="s1",
        from_email="talent@deepmind.com",
        subject="Research Scientist role for foundation models",
        body_text="We are selectively hiring a machine learning engineer for multimodal reasoning research.",
        received_at="2026-03-29T08:00:00+00:00",
    )
    result = classifier.classify(message)
    assert result.category == Category.STRONG_ML_RESEARCH_JOB
    assert result.suggested_action == SuggestedAction.NOTIFY_AND_DRAFT
    assert result.priority_score >= 0.75

