"""Created: 2026-04-06

Purpose: Verifies tolerant JSON parsing for local HuggingFace LLM outputs.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch

from src.llm.huggingface import HuggingFaceLLM, LLMGeneration


@dataclass(slots=True)
class FakeJsonLLM(HuggingFaceLLM):
    """Returns a fixed text payload instead of running a real model."""

    response_text: str = ""
    model_name: str = "fake/model"

    def generate_result(self, system_prompt: str, user_prompt: str) -> LLMGeneration:
        del system_prompt, user_prompt
        return LLMGeneration(content=self.response_text, raw_text=self.response_text)


def test_generate_json_repairs_missing_comma_between_fields() -> None:
    llm = FakeJsonLLM(
        response_text="""
        {
          "label": "job",
          "confidence": 0.91
          "reason": "Strong fit"
        }
        """
    )

    payload = llm.generate_json("sys", "user")

    assert payload == {
        "label": "job",
        "confidence": 0.91,
        "reason": "Strong fit",
    }


def test_generate_json_strips_code_fences_and_trailing_commas() -> None:
    llm = FakeJsonLLM(
        response_text="""```json
        {
          "label": "job",
          "confidence": 0.91,
        }
        ```"""
    )

    payload = llm.generate_json("sys", "user")

    assert payload == {
        "label": "job",
        "confidence": 0.91,
    }


def test_huggingface_uses_context_window_when_max_new_tokens_is_unset() -> None:
    llm = FakeJsonLLM()
    model = type("Model", (), {"config": type("Config", (), {"max_position_embeddings": 4096})()})()
    tokenizer = type("Tokenizer", (), {"model_max_length": 8192})()

    resolved = llm._resolve_max_new_tokens(model=model, prompt_tokens=512, tokenizer=tokenizer)

    assert resolved == 3584


def test_huggingface_prefers_explicit_max_new_tokens_when_provided() -> None:
    llm = FakeJsonLLM(max_new_tokens=256)
    model = type("Model", (), {"config": type("Config", (), {"max_position_embeddings": 4096})()})()
    tokenizer = type("Tokenizer", (), {"model_max_length": 8192})()

    resolved = llm._resolve_max_new_tokens(model=model, prompt_tokens=512, tokenizer=tokenizer)

    assert resolved == 256


class FakeBatch(dict):
    """Minimal tokenizer batch that supports `.to(...)`."""

    def to(self, device):
        return FakeBatch({key: value.to(device) for key, value in self.items()})


class FakeTokenizer:
    """Minimal tokenizer for kv-cache generation tests."""

    eos_token_id = 2
    model_max_length = 16

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True, enable_thinking=False):
        del tokenize, add_generation_prompt, enable_thinking
        return "\n".join(item["content"] for item in messages)

    def __call__(self, prompts, return_tensors="pt"):
        del prompts, return_tensors
        return FakeBatch(
            {
                "input_ids": torch.tensor([[10, 11, 12]], dtype=torch.long),
                "attention_mask": torch.tensor([[1, 1, 1]], dtype=torch.long),
            }
        )

    def decode(self, token_ids, skip_special_tokens=True):
        del skip_special_tokens
        if isinstance(token_ids, int):
            token_ids = [token_ids]
        return " ".join(str(token) for token in token_ids)


class FakeModel:
    """Records kv-cache usage across autoregressive steps."""

    def __init__(self) -> None:
        self.device = torch.device("cpu")
        self.config = type("Config", (), {"eos_token_id": 2, "max_position_embeddings": 16})()
        self.calls: list[dict[str, object]] = []
        self._next_tokens = [5, 6, 2]

    def __call__(self, *, input_ids, attention_mask, use_cache, past_key_values=None):
        self.calls.append(
            {
                "input_shape": tuple(input_ids.shape),
                "attention_shape": tuple(attention_mask.shape),
                "use_cache": use_cache,
                "has_past": past_key_values is not None,
            }
        )
        vocab_size = 8
        logits = torch.full((1, input_ids.shape[1], vocab_size), -1e9)
        next_token = self._next_tokens[len(self.calls) - 1]
        logits[0, -1, next_token] = 0.0
        return type(
            "Outputs",
            (),
            {
                "logits": logits,
                "past_key_values": ("cached", len(self.calls)),
            },
        )()


@dataclass(slots=True)
class FakeKVCachedLLM(HuggingFaceLLM):
    """Injects fake tokenizer/model pairs for kv-cache tests."""

    model_name: str = "fake/model"

    def __post_init__(self) -> None:
        self._tokenizer = FakeTokenizer()
        self._model = FakeModel()


def test_huggingface_generate_reuses_past_key_values_between_steps() -> None:
    llm = FakeKVCachedLLM(max_new_tokens=4, use_kv_chache=True)

    result = llm.generate_result("sys", "user")

    assert result.content == "5 6 2"
    assert llm._model.calls == [
        {"input_shape": (1, 3), "attention_shape": (1, 3), "use_cache": True, "has_past": False},
        {"input_shape": (1, 1), "attention_shape": (1, 4), "use_cache": True, "has_past": True},
        {"input_shape": (1, 1), "attention_shape": (1, 5), "use_cache": True, "has_past": True},
    ]
