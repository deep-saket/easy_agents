from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import uvicorn

from mailmind.container import AppContainer
from mailmind.core.models import EmailMessage
from mailmind.viewer.app import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mailmind")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db")

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
        item = container.orchestrator.execute_approval(args.approval_id)
        print(item.model_dump_json(indent=2))
        return

    if args.command == "reject":
        container.repository.init_db()
        item = container.orchestrator.reject_approval(args.approval_id, args.reason)
        print(item.model_dump_json(indent=2))
        return


if __name__ == "__main__":
    main()

