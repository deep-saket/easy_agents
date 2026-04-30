"""CLI entrypoint for the local Connections Agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from agents.connections_agent.agent import ConnectionsAgent


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Connections Agent locally.")
    parser.add_argument("message", nargs="?", help="Message/command for one turn.")
    parser.add_argument("--session-id", default="connections-demo", help="Conversation session id.")
    parser.add_argument(
        "--base-dir",
        default=str(Path(__file__).resolve().parent),
        help="Connections agent base directory containing data/ and runtime/.",
    )
    parser.add_argument("--interactive", action="store_true", help="Run interactive loop.")
    return parser


def run_interactive(agent: ConnectionsAgent, session_id: str) -> None:
    print("Connections Agent interactive mode. Type 'exit' to stop.")
    while True:
        try:
            message = input("you> ").strip()
        except EOFError:
            print()
            break
        if not message:
            continue
        if message.lower() in {"exit", "quit"}:
            break
        print(f"agent> {agent.run(message, session_id=session_id)}")


def main() -> None:
    args = build_arg_parser().parse_args()
    agent = ConnectionsAgent.from_local_files(base_dir=Path(args.base_dir))
    if args.interactive:
        run_interactive(agent, session_id=args.session_id)
        return
    if not args.message:
        raise SystemExit("message is required unless --interactive is set")
    print(agent.run(args.message, session_id=args.session_id))


if __name__ == "__main__":
    main()
