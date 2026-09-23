"""Command-line access to the complete declarative Specialist fleet."""

from __future__ import annotations

import argparse
import json
from typing import Any

from easy_agents.fleet.model_profiles import MAC_GEMMA_PROFILE_ID, build_fleet_mac_gemma
from easy_agents.fleet.models import MissionRequest, SpecialistStatus
from easy_agents.fleet.registry import FleetRegistry
from easy_agents.fleet.runtime import FleetRuntime


def build_parser() -> argparse.ArgumentParser:
    """Builds the fleet CLI parser."""

    parser = argparse.ArgumentParser(
        prog="easy-agents",
        description="Inspect, route, and safely run the Personal Agent Constellation.",
    )
    parser.add_argument("--compact", action="store_true", help="Print compact JSON.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List every compiled Specialist Charter.")
    list_parser.add_argument(
        "--status",
        choices=[item.value for item in SpecialistStatus],
        help="Filter by runtime lifecycle.",
    )

    inspect_parser = subparsers.add_parser("inspect", help="Inspect one Specialist Charter.")
    inspect_parser.add_argument("specialist_id")

    route_parser = subparsers.add_parser("route", help="Rank Specialists for a Mission.")
    route_parser.add_argument("objective", nargs="+")
    route_parser.add_argument("--limit", type=int, default=5)

    run_parser = subparsers.add_parser("run", help="Run a safe local advisory Mission.")
    run_parser.add_argument("objective", nargs="+")
    run_parser.add_argument("--agent", dest="specialist_id")
    run_parser.add_argument("--playbook", dest="preferred_playbook_id")
    run_parser.add_argument("--scope", dest="memory_scope")
    run_parser.add_argument("--effect", action="append", dest="requested_effects")
    run_parser.add_argument("--approve", action="append", dest="approved_effects")
    run_parser.add_argument("--allow-network", action="store_true")
    run_parser.add_argument("--team-size", type=int, default=1)
    run_parser.add_argument(
        "--model",
        choices=["none", "mac-gemma"],
        default="none",
        help="Use no model for a deterministic plan, or the loopback Gemma service.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Runs one registry or Mission command."""

    args = build_parser().parse_args(argv)
    registry = FleetRegistry.default()
    payload: Any
    if args.command == "list":
        status = SpecialistStatus(args.status) if args.status else None
        payload = {
            "summary": registry.summary(),
            "specialists": [
                item.model_dump(mode="json")
                for item in registry.list_specialists(status=status)
            ],
        }
    elif args.command == "inspect":
        payload = registry.get_specialist(args.specialist_id).model_dump(mode="json")
    elif args.command == "route":
        payload = {
            "objective": " ".join(args.objective),
            "candidates": [
                item.model_dump(mode="json")
                for item in registry.route(" ".join(args.objective), limit=args.limit)
            ],
        }
    else:
        llm = _build_model(args.model)
        request = MissionRequest(
            objective=" ".join(args.objective),
            specialist_id=args.specialist_id,
            preferred_playbook_id=args.preferred_playbook_id,
            memory_scope=args.memory_scope,
            requested_effects=args.requested_effects or ["read"],
            approved_effects=args.approved_effects or [],
            allow_network=args.allow_network,
            team_size=args.team_size,
            model_id=MAC_GEMMA_PROFILE_ID if llm is not None else "none",
        )
        models = {MAC_GEMMA_PROFILE_ID: llm} if llm is not None else {}
        payload = FleetRuntime(registry=registry, models=models).run(request).model_dump(mode="json")
    print(json.dumps(payload, indent=None if args.compact else 2, sort_keys=True))
    return 0


def _build_model(name: str) -> Any | None:
    if name == "none":
        return None
    client = build_fleet_mac_gemma()
    client.require_ready()
    return client


if __name__ == "__main__":
    raise SystemExit(main())
