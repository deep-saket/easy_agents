"""Command-line entry point for feature fit analysis."""

from __future__ import annotations

import argparse

from easy_agents.constellation.directory import ConstellationDirectory
from easy_agents.constellation.feature_intake import FeatureIntakeService


def build_parser() -> argparse.ArgumentParser:
    """Builds the feature-intake argument parser."""

    parser = argparse.ArgumentParser(
        prog="constellation-intake",
        description=(
            "Decide whether a feature should reuse, compose, extend, or create a "
            "specialist."
        ),
    )
    parser.add_argument("feature", nargs="+", help="Feature to assess in plain language.")
    parser.add_argument(
        "--catalog",
        help="Optional path to a custom constellation catalog YAML file.",
    )
    parser.add_argument("--compact", action="store_true", help="Print compact JSON.")
    return parser


def main() -> int:
    """Runs feature fit analysis and writes a JSON proposal to stdout."""

    args = build_parser().parse_args()
    directory = (
        ConstellationDirectory.from_yaml(args.catalog)
        if args.catalog
        else ConstellationDirectory.default()
    )
    proposal = FeatureIntakeService(directory).assess(" ".join(args.feature))
    print(proposal.model_dump_json(indent=None if args.compact else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
