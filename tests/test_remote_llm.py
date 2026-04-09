"""Created: 2026-04-09

Purpose: Verifies hosted endpoint llm integration behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel

from src.llm.factory import LLMFactory
from src.llm.remote_llm import EndpointLLM


class DemoSchema(BaseModel):
    """Represents a minimal structured response schema."""

    label: str
    confidence: float


@dataclass
class FakeHTTPResponse:
    """Provides a minimal urllib response context manager."""

    body: bytes

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    def read(self) -> bytes:
        return self.body


def test_endpoint_llm_posts_messages_and_parses_content(monkeypatch) -> None:
    llm = EndpointLLM(
        endpoint_url="https://example.test/generate",
        model_name="hosted-qwen",
        api_key="secret",
        max_new_tokens=64,
        default_headers={"X-Test": "1"},
        default_body={"temperature": 0.2},
    )
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeHTTPResponse(json.dumps({"content": "hello", "thinking_content": "plan"}).encode("utf-8"))

    monkeypatch.setattr("src.llm.remote_llm.request.urlopen", fake_urlopen)

    result = llm.generate_result("sys", "user")

    assert result.content == "hello"
    assert result.thinking_content == "plan"
    assert captured["url"] == "https://example.test/generate"
    assert captured["timeout"] == 300.0
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["headers"]["X-test"] == "1"
    assert captured["body"] == {
        "model": "hosted-qwen",
        "model_name": "hosted-qwen",
        "system_prompt": "sys",
        "user_prompt": "user",
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "user"},
        ],
        "max_new_tokens": 64,
        "temperature": 0.2,
    }


def test_endpoint_llm_parses_openai_style_choice_payload(monkeypatch) -> None:
    llm = EndpointLLM(endpoint_url="https://example.test/generate")

    def fake_urlopen(req, timeout):
        del req, timeout
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "{\"label\": \"job\", \"confidence\": 0.9}",
                        "reasoning": "short chain",
                    }
                }
            ]
        }
        return FakeHTTPResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr("src.llm.remote_llm.request.urlopen", fake_urlopen)

    payload = llm.generate_json("sys", "user")

    assert payload == {"label": "job", "confidence": 0.9}


def test_endpoint_llm_structured_generate_validates_schema(monkeypatch) -> None:
    llm = LLMFactory.build_endpoint_llm("https://example.test/generate", model_name="remote-model")

    def fake_urlopen(req, timeout):
        del req, timeout
        return FakeHTTPResponse(b'{"response": "{\"label\": \"job\", \"confidence\": 0.91}"}')

    monkeypatch.setattr("src.llm.remote_llm.request.urlopen", fake_urlopen)

    result = llm.structured_generate("classify", DemoSchema, system_prompt="json only")

    assert result.label == "job"
    assert result.confidence == 0.91


def test_factory_builds_openai_compatible_llm(monkeypatch) -> None:
    llm = LLMFactory.build_openai_compatible_llm(
        "https://llm.example.com",
        model_name="qwen-hosted",
        api_key="secret",
        max_new_tokens=128,
        temperature=0.1,
    )
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        payload = {"choices": [{"message": {"content": "hosted reply"}}]}
        return FakeHTTPResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr("src.llm.remote_llm.request.urlopen", fake_urlopen)

    result = llm.generate_result("sys", "user")

    assert result.content == "hosted reply"
    assert captured["url"] == "https://llm.example.com/v1/chat/completions"
    assert captured["timeout"] == 300.0
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["body"] == {
        "model": "qwen-hosted",
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "user"},
        ],
        "max_tokens": 128,
        "temperature": 0.1,
    }


def test_factory_builds_direct_openai_llm(monkeypatch) -> None:
    llm = LLMFactory.build_openai_llm(
        model_name="gpt-4o-mini",
        api_key="openai-secret",
        max_new_tokens=32,
    )
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        payload = {"choices": [{"message": {"content": "openai reply"}}]}
        return FakeHTTPResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr("src.llm.remote_llm.request.urlopen", fake_urlopen)

    result = llm.generate_result("sys", "user")

    assert result.content == "openai reply"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer openai-secret"
    assert captured["body"] == {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "user"},
        ],
        "max_tokens": 32,
    }


def test_factory_builds_direct_groq_llm(monkeypatch) -> None:
    llm = LLMFactory.build_groq_llm(
        model_name="llama-3.3-70b-versatile",
        api_key="groq-secret",
        max_new_tokens=48,
    )
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        payload = {"choices": [{"message": {"content": "groq reply"}}]}
        return FakeHTTPResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr("src.llm.remote_llm.request.urlopen", fake_urlopen)

    result = llm.generate_result("sys", "user")

    assert result.content == "groq reply"
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer groq-secret"
    assert captured["body"] == {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "user"},
        ],
        "max_tokens": 48,
    }
