"""Reusable model profiles for the Specialist Fleet."""

from __future__ import annotations

import os
from typing import Any

from llm.factory import LLMFactory


MAC_GEMMA_PROFILE_ID = "mac_gemma"


def build_fleet_mac_gemma() -> Any:
    """Builds a Fleet client for the external Mac-serving dependency.

    The model server and weights remain owned by the separate mac-serving
    repository. This profile only calls its documented loopback HTTP contract.
    A blank-line stop is disabled because the pretrained base model can begin a
    useful Fleet continuation with a blank line.
    """

    return LLMFactory.build_mac_gemma_llm(
        max_new_tokens=_env_int("EASY_AGENT_LLM_MAX_NEW_TOKENS", 256),
        temperature=_env_float("EASY_AGENT_LLM_TEMPERATURE", 0.2),
        top_p=_env_float("EASY_AGENT_LLM_TOP_P", 0.95),
        stop=(),
        timeout_seconds=_env_float("EASY_AGENT_LLM_TIMEOUT_SECONDS", 300.0),
    )


def mac_gemma_status(client: Any) -> dict[str, Any]:
    """Returns a bounded, credential-free readiness description."""

    ready = False
    models: list[str] = []
    error_type: str | None = None
    try:
        ready = bool(client.is_ready())
        if ready:
            models = [str(item) for item in client.list_models()]
    except Exception as exc:
        error_type = type(exc).__name__
    base_url = str(getattr(client, "base_url", "http://127.0.0.1:8080")).rstrip("/")
    return {
        "id": MAC_GEMMA_PROFILE_ID,
        "model": str(getattr(client, "model_name", "gemma-4-E4B")),
        "ready": ready,
        "models": models,
        "endpoint": f"{base_url}/v1/completions",
        "external_service": True,
        "contract_version": "1.0.0",
        "error_type": error_type,
    }


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None else int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value is None else float(value)
