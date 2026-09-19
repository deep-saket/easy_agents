"""Developer CLI for the native Mac Gemma completion service."""

from __future__ import annotations

import argparse
import json
import os

from .mac_gemma import DEFAULT_GEMMA_API_BASE, MacGemmaError, MacGemmaLLM


def build_parser() -> argparse.ArgumentParser:
    """Builds the local Gemma developer command parser."""

    parser = argparse.ArgumentParser(
        prog="local-gemma",
        description="Inspect or call the Mac-hosted Gemma completion service.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override GEMMA_API_BASE (default: http://127.0.0.1:8080).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ready", help="Check GET /readyz.")
    subparsers.add_parser("models", help="List GET /v1/models identifiers.")

    complete = subparsers.add_parser(
        "complete",
        help="Generate one raw, non-streaming base-model continuation.",
    )
    complete.add_argument("prompt", help="Raw text prompt to continue.")
    complete.add_argument("--max-tokens", type=int, default=128)
    complete.add_argument("--temperature", type=float, default=0.0)
    complete.add_argument("--top-p", type=float, default=0.95)
    complete.add_argument(
        "--stop",
        action="append",
        default=None,
        help="Repeatable stop string. Omit to use a blank-line stop.",
    )
    complete.add_argument(
        "--json",
        action="store_true",
        help="Print text, finish reason, and token usage as JSON.",
    )
    return parser


def main() -> int:
    """Executes one readiness, discovery, or completion command."""

    args = build_parser().parse_args()
    stop = tuple(args.stop) if getattr(args, "stop", None) is not None else ("\n\n",)
    client = MacGemmaLLM(
        base_url=(
            args.base_url
            or os.getenv("GEMMA_API_BASE")
            or DEFAULT_GEMMA_API_BASE
        ),
        api_key=os.getenv("MAC_SERVING_API_KEY"),
        max_tokens=getattr(args, "max_tokens", 128),
        temperature=getattr(args, "temperature", 0.0),
        top_p=getattr(args, "top_p", 0.95),
        stop=stop,
    )

    try:
        if args.command == "ready":
            if client.is_ready():
                print("ready")
                return 0
            print("not ready")
            return 1
        if args.command == "models":
            print(json.dumps(client.list_models(), indent=2))
            return 0

        result = client.generate_result(args.prompt)
        if args.json:
            print(
                json.dumps(
                    {
                        "text": result.content,
                        "finish_reason": result.finish_reason,
                        "usage": {
                            "prompt_tokens": result.prompt_tokens,
                            "completion_tokens": result.completion_tokens,
                            "total_tokens": result.total_tokens,
                        },
                    },
                    indent=2,
                )
            )
        else:
            print(result.content)
        return 0
    except MacGemmaError as exc:
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
