"""Explicitly enabled live smoke for the Mac-hosted Gemma service."""

from __future__ import annotations

import os

import pytest

from src.llm.factory import LLMFactory


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_LOCAL_GEMMA_LIVE") != "1",
        reason="Set RUN_LOCAL_GEMMA_LIVE=1 to call the local Gemma service.",
    ),
]


def test_local_gemma_readiness_discovery_and_completion() -> None:
    client = LLMFactory.build_mac_gemma_llm(
        max_new_tokens=16,
        temperature=0,
        stop=(),
    )

    client.require_ready()
    assert "gemma-4-E4B" in client.list_models()
    result = client.generate_result("The capital of France is")

    assert isinstance(result.content, str)
    assert result.content
    assert result.total_tokens is None or result.total_tokens > 0
