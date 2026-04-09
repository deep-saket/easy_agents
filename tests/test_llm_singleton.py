"""Created: 2026-04-06

Purpose: Verifies that LLM adapters are cached as singletons per configuration.
"""

from src.llm.factory import LLMFactory
from src.llm.function_gemma import FunctionGemmaLLM
from src.llm.qwen import Qwen3_1_7BLLM


def test_qwen_instances_are_singletons_per_configuration() -> None:
    first = Qwen3_1_7BLLM(model_name="Qwen/Qwen3-1.7B", max_new_tokens=128)
    second = Qwen3_1_7BLLM(model_name="Qwen/Qwen3-1.7B", max_new_tokens=128)

    assert first is second


def test_function_gemma_instances_are_singletons_per_configuration() -> None:
    first = FunctionGemmaLLM(model_name="google/functiongemma-270m-it", max_new_tokens=64)
    second = FunctionGemmaLLM(model_name="google/functiongemma-270m-it", max_new_tokens=64)

    assert first is second


def test_factory_returns_cached_wrappers() -> None:
    first = LLMFactory.build_default_local_llm()
    second = LLMFactory.build_default_local_llm()

    assert first is second
    assert first.client is second.client


def test_factory_accepts_hugging_face_repo_id_alias() -> None:
    model = LLMFactory.build_default_local_llm(model_name="Qwen/Qwen3-1.7B")

    assert model.client.model_name == "Qwen/Qwen3-1.7B"


def test_different_configurations_produce_distinct_instances() -> None:
    first = Qwen3_1_7BLLM(model_name="Qwen/Qwen3-1.7B", max_new_tokens=128)
    second = Qwen3_1_7BLLM(model_name="Qwen/Qwen3-1.7B", max_new_tokens=256)

    assert first is not second
