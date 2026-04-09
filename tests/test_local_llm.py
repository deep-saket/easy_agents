"""Created: 2026-04-06

Purpose: Verifies LocalLLM prompt shaping for plain and structured generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from src.llm.local_llm import LocalLLM


class DemoSchema(BaseModel):
    """Represents a simple schema for prompt injection tests."""

    label: str
    confidence: float


@dataclass(slots=True)
class RecordingClient:
    """Records prompts passed through LocalLLM."""

    generate_calls: list[tuple[str, str]] = field(default_factory=list)
    json_calls: list[tuple[str, str]] = field(default_factory=list)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.generate_calls.append((system_prompt, user_prompt))
        return "ok"

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        self.json_calls.append((system_prompt, user_prompt))
        return {"label": "job", "confidence": 0.91}


def test_local_llm_generate_uses_explicit_user_prompt() -> None:
    client = RecordingClient()
    llm = LocalLLM(client=client)

    response = llm.generate("ignored prompt", system_prompt="sys", user_prompt="real user prompt")

    assert response == "ok"
    assert client.generate_calls == [("sys", "real user prompt")]


def test_local_llm_structured_generate_appends_schema_to_user_prompt() -> None:
    client = RecordingClient()
    llm = LocalLLM(client=client)

    result = llm.structured_generate("classify this email", DemoSchema, system_prompt="json only")

    assert result.label == "job"
    assert result.confidence == 0.91
    system_prompt, user_prompt = client.json_calls[0]
    assert system_prompt == "json only"
    assert "classify this email" in user_prompt
    assert "Return one JSON object instance with exactly these fields" in user_prompt
    assert '"label": string; required' in user_prompt
    assert '"confidence": number; required' in user_prompt
    assert "Do not return a JSON schema." in user_prompt
