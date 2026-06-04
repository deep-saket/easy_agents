"""CLI entrypoint for ConversationManagerAgent."""

from __future__ import annotations

import argparse
from pathlib import Path

from agents.collection_agent.conversation_manager.runtime import ConversationManagedRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ConversationManagerAgent demo.")
    parser.add_argument("message", nargs="?", help="One turn input.")
    parser.add_argument("--session-id", default="conversation-manager-showcase", help="Session id")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--base-dir", default=str(Path(__file__).resolve().parent), help="Conversation manager directory")
    parser.add_argument(
        "--collection-base-dir",
        default=str(Path(__file__).resolve().parents[1]),
        help="Collection agent directory",
    )
    parser.add_argument("--user-code", default="user_a", choices=["user_a", "user_b", "user_c"])
    parser.add_argument("--soft-cap", type=int, default=10)
    parser.add_argument("--hard-cap", type=int, default=50)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser


def interactive(runtime: ConversationManagedRuntime, *, session_id: str, soft_cap: int, hard_cap: int, timeout_seconds: float) -> None:
    print("ConversationManagerAgent interactive mode. Type 'exit' to stop.")
    while True:
        try:
            text = input("you> ").strip()
        except EOFError:
            print()
            break
        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            break
        result = runtime.run_turn(
            RunTurnRequest(
                message=text,
                session_id=session_id,
                sender="customer",
                soft_cap=soft_cap,
                hard_cap=hard_cap,
                timeout_seconds=timeout_seconds,
            )
        )
        print(f"agent> {str(result.get('final_response', '')).strip()}")


def main() -> None:
    from agents.collection_agent.ui.server import RunTurnRequest, StartConversationRequest

    args = build_parser().parse_args()
    runtime = ConversationManagedRuntime.create(
        base_dir=Path(args.base_dir).resolve(),
        collection_base_dir=Path(args.collection_base_dir).resolve(),
    )

    start_payload = runtime.start_conversation(
        StartConversationRequest(
            user_code=args.user_code,
            session_id=args.session_id,
            soft_cap=max(1, int(args.soft_cap)),
            hard_cap=max(max(1, int(args.soft_cap)), int(args.hard_cap)),
        )
    )
    opener = str(((start_payload.get("turn") or {}).get("final_response")) or "").strip()
    if opener:
        print(f"agent> {opener}")

    if args.interactive:
        interactive(
            runtime,
            session_id=args.session_id,
            soft_cap=max(1, int(args.soft_cap)),
            hard_cap=max(max(1, int(args.soft_cap)), int(args.hard_cap)),
            timeout_seconds=max(1.0, float(args.timeout_seconds)),
        )
        return

    if not args.message:
        raise SystemExit("message is required unless --interactive is used")

    result = runtime.run_turn(
        RunTurnRequest(
            message=args.message,
            session_id=args.session_id,
            sender="customer",
            soft_cap=max(1, int(args.soft_cap)),
            hard_cap=max(max(1, int(args.soft_cap)), int(args.hard_cap)),
            timeout_seconds=max(1.0, float(args.timeout_seconds)),
        )
    )
    print(str(result.get("final_response", "")).strip())


if __name__ == "__main__":
    main()
