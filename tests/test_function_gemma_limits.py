"""Created: 2026-04-06

Purpose: Verifies dynamic max-new-token resolution for Function Gemma.
"""

from src.llm.function_gemma import FunctionGemmaLLM


def test_function_gemma_uses_context_window_when_max_new_tokens_is_unset() -> None:
    llm = FunctionGemmaLLM()
    model = type("Model", (), {"config": type("Config", (), {"max_position_embeddings": 2048})()})()

    resolved = llm._resolve_max_new_tokens(model=model, prompt_tokens=256)

    assert resolved == 1792


def test_function_gemma_prefers_explicit_max_new_tokens_when_provided() -> None:
    llm = FunctionGemmaLLM(max_new_tokens=128)
    model = type("Model", (), {"config": type("Config", (), {"max_position_embeddings": 2048})()})()

    resolved = llm._resolve_max_new_tokens(model=model, prompt_tokens=256)

    assert resolved == 128
