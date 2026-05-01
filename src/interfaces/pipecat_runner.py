"""Created: 2026-05-01

Purpose: Shared Pipecat runner integration helpers for Easy Agent runtimes.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping


class PipecatNotInstalledError(RuntimeError):
    """Raised when Pipecat integration is requested but dependencies are missing."""


@dataclass(slots=True)
class PipecatRunnerConfig:
    """Configuration for Pipecat development runner transports and audio settings."""

    enabled: bool = False
    vad_enabled: bool = True
    audio_in_sample_rate: int = 16000
    audio_out_sample_rate: int = 24000

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "PipecatRunnerConfig":
        """Builds config from a runtime mapping."""

        data = dict(payload or {})
        return cls(
            enabled=bool(data.get("enabled", False)),
            vad_enabled=bool(data.get("vad_enabled", True)),
            audio_in_sample_rate=int(data.get("audio_in_sample_rate", 16000)),
            audio_out_sample_rate=int(data.get("audio_out_sample_rate", 24000)),
        )


def ensure_pipecat_available() -> None:
    """Ensures Pipecat is importable before runtime boot."""

    try:
        importlib.import_module("pipecat")
    except ModuleNotFoundError as exc:
        raise PipecatNotInstalledError(
            "Pipecat is not installed. Install with: pip install 'pipecat-ai[runner,websocket,openai]'"
        ) from exc


def build_transport_params(
    *,
    vad_enabled: bool = True,
) -> dict[str, Callable[[], Any]]:
    """Builds transport parameter factories for runner-supported transports."""

    ensure_pipecat_available()

    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.daily.transport import DailyParams
    from pipecat.transports.network.fastapi_websocket import FastAPIWebsocketParams

    vad_analyzer = None
    if vad_enabled:
        try:
            from pipecat.audio.vad.silero import SileroVADAnalyzer

            vad_analyzer = SileroVADAnalyzer()
        except Exception:
            vad_analyzer = None

    return {
        "daily": lambda: DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=vad_analyzer,
        ),
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=vad_analyzer,
        ),
        "twilio": lambda: FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=vad_analyzer,
        ),
        "telnyx": lambda: FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=vad_analyzer,
        ),
        "plivo": lambda: FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=vad_analyzer,
        ),
        "exotel": lambda: FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=vad_analyzer,
        ),
    }


def build_runner_bot(
    *,
    run_bot: Callable[[Any, Any], Awaitable[None]],
    transport_params: Mapping[str, Callable[[], Any]],
) -> Callable[[Any], Awaitable[None]]:
    """Builds a Pipecat runner-compatible `bot(runner_args)` coroutine."""

    ensure_pipecat_available()

    from pipecat.runner.utils import create_transport

    async def bot(runner_args: Any) -> None:
        transport = await create_transport(runner_args, dict(transport_params))
        await run_bot(transport, runner_args)

    return bot


def run_pipecat_main() -> None:
    """Delegates process execution to Pipecat's development runner main."""

    ensure_pipecat_available()

    from pipecat.runner.run import main

    # Keep ENV behavior explicit for local development defaults.
    os.environ.setdefault("ENV", "local")
    main()


__all__ = [
    "PipecatNotInstalledError",
    "PipecatRunnerConfig",
    "build_runner_bot",
    "build_transport_params",
    "ensure_pipecat_available",
    "run_pipecat_main",
]
