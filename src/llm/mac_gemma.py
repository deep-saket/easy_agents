"""Client for the native Mac Gemma llama.cpp completion service."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from urllib import error, request

from .base import BaseLLM
from .huggingface import HuggingFaceLLM, LLMGeneration

try:
    from src.platform_logging.tracing import record_llm_call
except ModuleNotFoundError:  # Installed package exposes platform_logging directly.
    from platform_logging.tracing import record_llm_call


DEFAULT_GEMMA_API_BASE = "http://127.0.0.1:8080"
DEFAULT_GEMMA_MODEL = "gemma-4-E4B"
GEMMA_CONTEXT_TOKENS = 16_384


class MacGemmaError(RuntimeError):
    """A bounded, credential-safe error from the local Gemma service."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(slots=True)
class MacGemmaLLM(BaseLLM):
    """Calls the Mac-hosted Gemma base model through ``/v1/completions``.

    The served model is pretrained rather than instruction tuned. ``generate``
    therefore concatenates system and user material into one raw continuation
    prompt instead of inventing a chat template.
    """

    base_url: str = DEFAULT_GEMMA_API_BASE
    model_name: str = DEFAULT_GEMMA_MODEL
    api_key: str | None = field(default=None, repr=False)
    max_tokens: int = 128
    temperature: float = 0.0
    top_p: float = 0.95
    stop: tuple[str, ...] = ("\n\n",)
    timeout_seconds: float = 300.0
    readiness_timeout_seconds: float = 3.0
    max_retries: int = 1
    retry_backoff_seconds: float = 0.2

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if not self.base_url:
            raise ValueError("Gemma base_url must not be empty.")
        if self.model_name != DEFAULT_GEMMA_MODEL:
            raise ValueError(
                f"Mac Gemma service exposes {DEFAULT_GEMMA_MODEL!r}; "
                f"received {self.model_name!r}."
            )
        self._validate_generation_options(
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
        )
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative.")

    def is_ready(self) -> bool:
        """Returns whether the service reports a ready inference backend."""

        try:
            payload = self._request_json(
                method="GET",
                path="/readyz",
                timeout_seconds=self.readiness_timeout_seconds,
                retry=False,
            )
        except MacGemmaError:
            return False
        return isinstance(payload, dict) and payload.get("status") == "ready"

    def require_ready(self) -> None:
        """Raises a useful error when the local service is unavailable."""

        if not self.is_ready():
            raise MacGemmaError(
                "Local Gemma is not ready. Start it with:\n"
                "cd /Users/saketm10/Projects/foundation-ai-platform/mac-serving\n"
                ".venv/bin/mac-serve serve"
            )

    def list_models(self) -> list[str]:
        """Returns model identifiers advertised by ``GET /v1/models``."""

        payload = self._request_json(
            method="GET",
            path="/v1/models",
            timeout_seconds=self.readiness_timeout_seconds,
            retry=False,
        )
        if not isinstance(payload, dict):
            raise MacGemmaError("Gemma model discovery returned a non-object response.")

        identifiers: list[str] = []
        data = payload.get("data")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("id"):
                    identifiers.append(str(item["id"]))

        models = payload.get("models")
        if isinstance(models, list):
            for item in models:
                if not isinstance(item, dict):
                    continue
                value = item.get("model") or item.get("name")
                if value:
                    identifiers.append(str(value))
        return list(dict.fromkeys(identifiers))

    def generate(
        self,
        system_prompt: str,
        user_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Returns one non-streaming raw text completion."""

        return self.generate_result(system_prompt, user_prompt, **kwargs).content

    def generate_result(
        self,
        system_prompt: str,
        user_prompt: str | None = None,
        **kwargs: Any,
    ) -> LLMGeneration:
        """Returns text, finish reason, and portable token usage."""

        prompt = self.compose_prompt(system_prompt, user_prompt)
        max_tokens = int(kwargs.pop("max_tokens", self.max_tokens))
        temperature = float(kwargs.pop("temperature", self.temperature))
        top_p = float(kwargs.pop("top_p", self.top_p))
        stop = self._normalize_stop(kwargs.pop("stop", self.stop))
        if kwargs:
            unsupported = ", ".join(sorted(kwargs))
            raise TypeError(f"Unsupported Gemma generation options: {unsupported}")
        self._validate_generation_options(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
            "stop": list(stop),
        }
        started = perf_counter()
        response = self._request_json(
            method="POST",
            path="/v1/completions",
            payload=payload,
            timeout_seconds=self.timeout_seconds,
            retry=True,
        )
        result = self._parse_completion(response)
        record_llm_call(
            model_name=self.model_name,
            call_kind="generate",
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            duration_ms=round((perf_counter() - started) * 1000, 3),
        )
        return result

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Parses a JSON object from a non-streaming completion."""

        response = self.generate(system_prompt, user_prompt, stop=())
        candidate = HuggingFaceLLM._extract_json_object(response)
        return HuggingFaceLLM._load_dirty_json(candidate)

    def structured_generate(self, prompt: str, schema: type, **kwargs: Any) -> Any:
        """Validates a JSON completion against a caller-provided schema.

        Because this is a base model, callers should supply demonstrations or a
        continuation format that has been evaluated for the target task.
        """

        system_prompt = kwargs.pop(
            "system_prompt",
            "Continue with one JSON object and no surrounding prose.",
        )
        if kwargs:
            unsupported = ", ".join(sorted(kwargs))
            raise TypeError(f"Unsupported structured Gemma options: {unsupported}")
        schema_json = json.dumps(
            schema.model_json_schema(),
            separators=(",", ":"),
            sort_keys=True,
        )
        structured_prompt = (
            f"{prompt.rstrip()}\n\n"
            "Continue with one JSON object that satisfies this JSON Schema:\n"
            f"{schema_json}\nJSON:"
        )
        payload = self.generate_json(system_prompt, structured_prompt)
        return schema.model_validate(payload)

    @staticmethod
    def compose_prompt(system_prompt: str, user_prompt: str | None = None) -> str:
        """Combines two legacy agent prompt fields without a chat template."""

        if user_prompt is None:
            return system_prompt
        if not system_prompt:
            return user_prompt
        if not user_prompt:
            return system_prompt
        return f"{system_prompt.rstrip()}\n\n{user_prompt.lstrip()}"

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        timeout_seconds: float,
        payload: dict[str, Any] | None = None,
        retry: bool,
    ) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        attempts = self.max_retries + 1 if retry else 1
        for attempt in range(attempts):
            req = request.Request(
                f"{self.base_url}{path}",
                data=body,
                headers=headers,
                method=method,
            )
            try:
                with request.urlopen(req, timeout=timeout_seconds) as response:
                    response_body = response.read().decode("utf-8")
                return json.loads(response_body)
            except error.HTTPError as exc:
                diagnostic = self._read_error_body(exc)
                if exc.code == 503 and attempt + 1 < attempts:
                    self._backoff(attempt)
                    continue
                raise self._http_error(exc.code, diagnostic) from exc
            except error.URLError as exc:
                if attempt + 1 < attempts:
                    self._backoff(attempt)
                    continue
                reason = self._redact(str(exc.reason))
                raise MacGemmaError(
                    f"Could not connect to local Gemma at {self.base_url}: {reason}"
                ) from exc
            except json.JSONDecodeError as exc:
                raise MacGemmaError(
                    "Local Gemma returned invalid JSON for "
                    f"{method} {path}."
                ) from exc

        raise MacGemmaError("Local Gemma request exhausted all attempts.")

    def _http_error(self, status_code: int, diagnostic: str) -> MacGemmaError:
        if status_code == 401:
            message = "Local Gemma rejected authentication (401)."
        elif status_code == 400:
            message = "Local Gemma rejected the completion request (400)."
        elif status_code == 503:
            message = "Local Gemma inference backend is unavailable (503)."
        else:
            message = f"Local Gemma request failed with HTTP {status_code}."
        if diagnostic:
            message = f"{message} {diagnostic}"
        return MacGemmaError(message, status_code=status_code)

    def _read_error_body(self, exc: error.HTTPError) -> str:
        try:
            raw = exc.read(512).decode("utf-8", errors="replace").strip()
        except Exception:
            return ""
        return self._redact(raw[:512])

    def _redact(self, value: str) -> str:
        if self.api_key:
            return value.replace(self.api_key, "[REDACTED]")
        return value

    def _backoff(self, attempt: int) -> None:
        if self.retry_backoff_seconds <= 0:
            return
        time.sleep(self.retry_backoff_seconds * (2**attempt))

    @staticmethod
    def _parse_completion(payload: Any) -> LLMGeneration:
        if not isinstance(payload, dict):
            raise MacGemmaError("Gemma completion response must be a JSON object.")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise MacGemmaError("Gemma completion response is missing choices[0].")
        text = choices[0].get("text")
        if not isinstance(text, str):
            raise MacGemmaError("Gemma completion response is missing choices[0].text.")

        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        prompt_tokens = MacGemmaLLM._optional_int(usage.get("prompt_tokens"))
        completion_tokens = MacGemmaLLM._optional_int(usage.get("completion_tokens"))
        total_tokens = MacGemmaLLM._optional_int(usage.get("total_tokens"))
        return LLMGeneration(
            content=text,
            raw_text=text,
            finish_reason=MacGemmaLLM._optional_text(choices[0].get("finish_reason")),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _normalize_stop(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
            return tuple(value)
        raise TypeError("stop must be a string, a sequence of strings, or None.")

    @staticmethod
    def _validate_generation_options(
        *,
        max_tokens: int,
        temperature: float,
        top_p: float,
    ) -> None:
        if not 1 <= max_tokens <= GEMMA_CONTEXT_TOKENS:
            raise ValueError(
                f"max_tokens must be between 1 and {GEMMA_CONTEXT_TOKENS}."
            )
        if temperature < 0:
            raise ValueError("temperature must be non-negative.")
        if not 0 < top_p <= 1:
            raise ValueError("top_p must be greater than 0 and at most 1.")
