"""Created: 2026-09-24

Purpose: Provides validation, inspection, and routing commands for Galaxy catalogs.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from easy_agents.galaxy.catalog import load_galaxy
from easy_agents.galaxy.compatibility import registry_from_fleet
from easy_agents.galaxy.missions import Mission, MissionBudget
from easy_agents.galaxy.routing import Wormhole
from easy_agents.galaxy.schemas import GalaxySnapshotV2


def build_parser() -> argparse.ArgumentParser:
    """Builds the public ``easy-agents-galaxy`` argument parser."""

    parser = argparse.ArgumentParser(
        prog="easy-agents-galaxy",
        description="Validate, inspect, and route canonical Galaxy catalogs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("validate", "validate a Galaxy catalog and print its entity counts"),
        ("show", "print the normalized version-2 snapshot as JSON"),
    ):
        child = subparsers.add_parser(name, help=help_text)
        _add_source_arguments(child)

    route = subparsers.add_parser("route", help="route a Mission without executing effects")
    _add_source_arguments(route)
    route.add_argument("objective", help="natural-language Mission objective")
    route.add_argument("--galaxy", dest="galaxy_id")
    route.add_argument("--circle", dest="circle_id")
    route.add_argument("--planet", dest="planet_id")
    route.add_argument("--team-size", type=int, default=1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Runs a Galaxy CLI command.

    Args:
        argv: Optional arguments excluding the executable name. ``None`` reads
            the current process arguments.

    Returns:
        Process exit code: zero for success and two for validation/routing
        errors.
    """

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        registry = _load_registry(args)
        if args.command == "validate":
            print(json.dumps({"status": "valid", "summary": registry.summary()}, indent=2))
        elif args.command == "show":
            snapshot = GalaxySnapshotV2.from_registry(registry)
            print(snapshot.model_dump_json(indent=2))
        else:
            mission = Mission(
                objective=args.objective,
                galaxy_id=args.galaxy_id,
                preferred_circle_id=args.circle_id,
                preferred_planet_id=args.planet_id,
                team_size=args.team_size,
                budget=MissionBudget(max_planets=args.team_size),
            )
            print(Wormhole(registry).route(mission).model_dump_json(indent=2))
    except (KeyError, OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds mutually exclusive catalog-source options to a command."""

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--catalog", help="path to a version-2 Galaxy YAML file")
    source.add_argument(
        "--current-fleet",
        action="store_true",
        help="adapt the packaged version-1 fleet without modifying it",
    )


def _load_registry(args: argparse.Namespace):
    """Loads the selected YAML or current v1 compatibility source."""

    if args.current_fleet:
        from easy_agents.fleet.registry import FleetRegistry

        return registry_from_fleet(FleetRegistry.default())
    return load_galaxy(args.catalog)


if __name__ == "__main__":
    raise SystemExit(main())
