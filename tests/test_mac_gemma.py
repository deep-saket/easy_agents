"""Contract tests for the native Mac Gemma completion client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO
from urllib import error

import pytest
from pydantic import BaseModel

from agents.collection_agent.main import build_llm as build_collection_llm
from agents.mailmind.main import build_llm as build_mailmind_llm
from src.llm.factory import LLMFactory
from src.llm.mac_gemma import MacGemmaError, MacGemmaLLM
from src.utils.config import AppSettings


@dataclass
class FakeHTTPResponse:
    """Minimal urllib response context manager."""

    body: bytes

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    def read(self) -> bytes:
        return self.body


class Classification(BaseModel):
    label: str


def test_completion_uses_v1_completions_and_portable_fields(monkeypatch) -> None:
    client = MacGemmaLLM(
        base_url="http://127.0.0.1:18080/",
        api_key="local-secret",
        max_tokens=32,
        temperature=0.0,
        top_p=0.9,
        stop=("END",),
    )
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.method
        captured["timeout"] = timeout
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeHTTPResponse(
            json.dumps(
                {
                    "choices": [{"text": " continued", "finish_reason": "stop"}],
                    "usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": 2,
                        "total_tokens": 7,
                    },
                    "timings": {"ignored": True},
                }
            ).encode("utf-8")
        )

    monkeypatch.setattr("src.llm.mac_gemma.request.urlopen", fake_urlopen)

    result = client.generate_result("System prefix", "User suffix")

    assert result.content == " continued"
    assert result.finish_reason == "stop"
    assert result.prompt_tokens == 5
    assert result.completion_tokens == 2
    assert result.total_tokens == 7
    assert captured["url"] == "http://127.0.0.1:18080/v1/completions"
    assert captured["method"] == "POST"
    assert captured["headers"]["Authorization"] == "Bearer local-secret"
    assert captured["body"] == {
        "model": "gemma-4-E4B",
        "prompt": "System prefix\n\nUser suffix",
        "max_tokens": 32,
        "temperature": 0.0,
        "top_p": 0.9,
        "stream": False,
        "stop": ["END"],
    }


def test_readiness_and_model_discovery(monkeypatch) -> None:
    client = MacGemmaLLM(base_url="http://127.0.0.1:18081")
    calls: list[tuple[str, str]] = []

    def fake_urlopen(req, timeout):
        calls.append((req.full_url, req.method))
        assert timeout == 3.0
        if req.full_url.endswith("/readyz"):
            return FakeHTTPResponse(b'{"status":"ready"}')
        return FakeHTTPResponse(
            b'{"models":[{"name":"gemma-4-E4B"}],'
            b'"data":[{"id":"gemma-4-E4B"}]}'
        )

    monkeypatch.setattr("src.llm.mac_gemma.request.urlopen", fake_urlopen)

    assert client.is_ready() is True
    assert client.list_models() == ["gemma-4-E4B"]
    assert calls == [
        ("http://127.0.0.1:18081/readyz", "GET"),
        ("http://127.0.0.1:18081/v1/models", "GET"),
    ]


def test_factory_reads_environment_without_logging_key(monkeypatch) -> None:
    monkeypatch.setenv("GEMMA_API_BASE", "http://127.0.0.1:18082")
    monkeypatch.setenv("MAC_SERVING_API_KEY", "do-not-print")

    client = LLMFactory.build_mac_gemma_llm(max_new_tokens=16)

    assert client.base_url == "http://127.0.0.1:18082"
    assert client.api_key == "do-not-print"
    assert "do-not-print" not in repr(client)


def test_authentication_error_redacts_api_key(monkeypatch) -> None:
    client = MacGemmaLLM(
        base_url="http://127.0.0.1:18083",
        api_key="sensitive-key",
        max_retries=0,
    )

    def fake_urlopen(req, timeout):
        del req, timeout
        raise error.HTTPError(
            url="http://127.0.0.1:18083/v1/completions",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=BytesIO(b'{"error":"sensitive-key is invalid"}'),
        )

    monkeypatch.setattr("src.llm.mac_gemma.request.urlopen", fake_urlopen)

    with pytest.raises(MacGemmaError) as exc_info:
        client.generate("Continue:")

    assert exc_info.value.status_code == 401
    assert "sensitive-key" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_503_is_retried_once(monkeypatch) -> None:
    client = MacGemmaLLM(
        base_url="http://127.0.0.1:18084",
        max_retries=1,
        retry_backoff_seconds=0,
    )
    calls = 0

    def fake_urlopen(req, timeout):
        nonlocal calls
        del req, timeout
        calls += 1
        if calls == 1:
            raise error.HTTPError(
                url="http://127.0.0.1:18084/v1/completions",
                code=503,
                msg="Unavailable",
                hdrs=None,
                fp=BytesIO(b'{"error":"loading"}'),
            )
        return FakeHTTPResponse(b'{"choices":[{"text":"ok"}],"usage":{}}')

    monkeypatch.setattr("src.llm.mac_gemma.request.urlopen", fake_urlopen)

    assert client.generate("Continue:") == "ok"
    assert calls == 2


def test_generation_options_are_bounded() -> None:
    with pytest.raises(ValueError, match="between 1 and 16384"):
        MacGemmaLLM(max_tokens=16_385)
    with pytest.raises(ValueError, match="top_p"):
        MacGemmaLLM(top_p=0)


def test_structured_generation_includes_schema(monkeypatch) -> None:
    client = MacGemmaLLM(base_url="http://127.0.0.1:18087")
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):
        del timeout
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeHTTPResponse(
            b'{"choices":[{"text":"{\\\"label\\\":\\\"science\\\"}"}]}'
        )

    monkeypatch.setattr("src.llm.mac_gemma.request.urlopen", fake_urlopen)

    result = client.structured_generate("Classify this article.", Classification)

    assert result == Classification(label="science")
    prompt = captured["body"]["prompt"]
    assert '"properties":{"label"' in prompt
    assert prompt.endswith("JSON:")


def test_mailmind_and_collection_build_mac_gemma_provider(monkeypatch) -> None:
    monkeypatch.delenv("MAC_SERVING_API_KEY", raising=False)
    settings = AppSettings.model_validate(
        {
            "llm": {
                "provider": "mac_gemma",
                "model_name": "gemma-4-E4B",
                "base_url": "http://127.0.0.1:18085",
                "max_new_tokens": 24,
            }
        }
    )

    mailmind = build_mailmind_llm(settings)
    collection = build_collection_llm(
        {
            "llm": {
                "enabled": True,
                "provider": "mac_gemma",
                "model_name": "gemma-4-E4B",
                "base_url": "http://127.0.0.1:18086",
                "max_new_tokens": 24,
            }
        }
    )

    assert isinstance(mailmind, MacGemmaLLM)
    assert mailmind.base_url == "http://127.0.0.1:18085"
    assert isinstance(collection, MacGemmaLLM)
    assert collection.base_url == "http://127.0.0.1:18086"
