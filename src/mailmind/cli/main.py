"""Created: 2026-03-30

Purpose: Implements the main module for the shared mailmind platform layer.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import uvicorn

from agents.mailmind.agent import MailMindAgentApp
from mailmind.container import AppContainer
from mailmind.core.models import EmailMessage
from mailmind.viewer.app import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mailmind")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db")
    fetch = subparsers.add_parser("fetch-emails")
    fetch.add_argument("--no-process", action="store_true")

    classify = subparsers.add_parser("classify-emails")
    classify.add_argument("message_ids", nargs="+")

    list_emails = subparsers.add_parser("list-emails")
    list_emails.add_argument("--query")
    list_emails.add_argument("--category")
    list_emails.add_argument("--sender")
    list_emails.add_argument("--important", action="store_true")

    run_agent = subparsers.add_parser("run-agent")
    run_agent.add_argument("query")
    run_agent.add_argument("--session-id", default="cli-default")

    run_chat = subparsers.add_parser("run-chat")
    run_chat.add_argument("--session-id", default="cli-chat")

    run_whatsapp = subparsers.add_parser("run-whatsapp-mock")
    run_whatsapp.add_argument("text")
    run_whatsapp.add_argument("--session-id", default="whatsapp-demo")

    poller = subparsers.add_parser("run-poller")
    poller.add_argument("--once", action="store_true", help="Process a single polling cycle.")

    subparsers.add_parser("run-viewer")

    reprocess = subparsers.add_parser("reprocess-email")
    reprocess.add_argument("message_id")

    approve = subparsers.add_parser("approve")
    approve.add_argument("approval_id")

    reject = subparsers.add_parser("reject")
    reject.add_argument("approval_id")
    reject.add_argument("--reason", default="Rejected by operator.")

    seed = subparsers.add_parser("seed-demo-data")
    seed.add_argument("--path", default="data/seed/demo_messages.json")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    container = AppContainer.from_env()

    if args.command == "init-db":
        container.repository.init_db()
        print(f"Initialized SQLite database at {container.settings.db_path}")
        return

    if args.command == "fetch-emails":
        container.repository.init_db()
        result = container.tool_executor.execute("gmail_fetch", {"process_messages": not args.no_process})
        print(json.dumps(result, indent=2))
        return

    if args.command == "classify-emails":
        container.repository.init_db()
        result = container.tool_executor.execute("email_classifier", {"message_ids": args.message_ids})
        print(json.dumps(result, indent=2))
        return

    if args.command == "list-emails":
        container.repository.init_db()
        result = container.tool_executor.execute(
            "email_search",
            {
                "query": args.query,
                "category": args.category,
                "sender": args.sender,
                "only_important": args.important,
            },
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "run-agent":
        container.repository.init_db()
        result = MailMindAgentApp.from_env().run(args.query, args.session_id)
        print(result)
        return

    if args.command == "run-chat":
        container.repository.init_db()
        app = MailMindAgentApp.from_env()
        print(f"Chat session: {args.session_id}")
        while True:
            user_input = input("You: ").strip()
            if user_input.lower() in {"exit", "quit"}:
                break
            response = app.run(user_input, args.session_id)
            print(f"Agent: {response}")
        return

    if args.command == "run-whatsapp-mock":
        container.repository.init_db()
        app = MailMindAgentApp.from_env()
        response = app.run(args.text, args.session_id)
        container.whatsapp_interface.send_message(args.session_id, response)
        print(response)
        return

    if args.command == "seed-demo-data":
        container.repository.init_db()
        records = json.loads(Path(args.path).read_text(encoding="utf-8"))
        messages = [EmailMessage.model_validate(record) for record in records]
        bundles = container.orchestrator.process_messages(messages)
        print(f"Seeded {len(bundles)} messages from {args.path}")
        return

    if args.command == "run-poller":
        container.repository.init_db()
        if args.once:
            bundles = container.orchestrator.process_messages(container.source.fetch_new_messages())
            print(f"Processed {len(bundles)} new messages")
            return
        while True:
            bundles = container.orchestrator.process_messages(container.source.fetch_new_messages())
            print(f"Processed {len(bundles)} new messages")
            time.sleep(container.settings.poll_seconds)

    if args.command == "run-viewer":
        container.repository.init_db()
        app = create_app(container)
        uvicorn.run(app, host=container.settings.viewer_host, port=container.settings.viewer_port)
        return

    if args.command == "reprocess-email":
        container.repository.init_db()
        bundle = container.orchestrator.reprocess(args.message_id)
        print(bundle.model_dump_json(indent=2))
        return

    if args.command == "approve":
        container.repository.init_db()
        result = container.tool_executor.execute("notification", {"approval_id": args.approval_id})
        print(json.dumps(result, indent=2))
        return

    if args.command == "reject":
        container.repository.init_db()
        item = container.orchestrator.reject_approval(args.approval_id, args.reason)
        print(item.model_dump_json(indent=2))
        return


if __name__ == "__main__":
    main()
