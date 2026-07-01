"""Story wizard CLI command placeholder."""

from __future__ import annotations

import argparse


def _run(_args: argparse.Namespace) -> int:
    print("story wizard commands are not implemented in this MVP")
    return 1


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register wizard command."""
    parser = subparsers.add_parser("wizard", help="Story wizard commands.")
    parser.set_defaults(handler=_run)


def main(argv: list[str] | None = None) -> int:
    """Run wizard directly."""
    parser = argparse.ArgumentParser(description="Wizard command.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register(subparsers)
    args = parser.parse_args(["wizard", *(argv or [])])
    return int(args.handler(args) or 0)
