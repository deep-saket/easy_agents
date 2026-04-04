"""Created: 2026-04-02

Purpose: Tests the reusable intent node behavior.
"""

from src.nodes import IntentNode


def test_intent_node_parses_json_intent_payload() -> None:
    """Verifies that the node extracts intent data from llm JSON output."""

    class FakeLLM:
        def generate(self, system_prompt: str, user_prompt: str) -> str:
            del system_prompt
            assert '"calculate"' in user_prompt
            return '{"intent": "calculate", "confidence": 0.92, "reason": "Arithmetic request."}'

    node = IntentNode(
        llm=FakeLLM(),
        system_prompt="Classify the user intent.",
        user_prompt='Input: {user_input}\nLabels: {intent_labels}',
        intent_labels=["calculate", "convert", "chat"],
    )

    result = node.execute({"user_input": "what is 12 * 7?"})

    assert result["intent"]["intent"] == "calculate"
    assert result["intent"]["confidence"] == 0.92
    assert result["intent"]["reason"] == "Arithmetic request."


def test_intent_node_uses_default_without_llm() -> None:
    """Verifies the deterministic fallback path when no llm is configured."""
    node = IntentNode(default_intent="general", default_confidence=0.1)

    result = node.execute({"user_input": "hello"})

    assert result["intent"]["intent"] == "general"
    assert result["intent"]["confidence"] == 0.1
