"""Created: 2026-03-30

Purpose: Tests the policy provider behavior.
"""

from pathlib import Path

from src.mailmind.core.policies import YAMLPolicyProvider


def test_policy_provider_loads_default_policy() -> None:
    provider = YAMLPolicyProvider(Path("policies/default_policy.yaml"))
    policy = provider.load()
    assert policy.high_priority_threshold == 0.75
    assert "strong_ml_research_job" in policy.positive_keywords

