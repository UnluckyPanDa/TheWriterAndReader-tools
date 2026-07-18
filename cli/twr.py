"""CLI entrypoint for TheWriterAndReader tools."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TOOLS_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_REPO_ROOT))

from cli.commands import config, doctor, publish, review, setup, web, wizard, write


def build_parser() -> argparse.ArgumentParser:
    """Build the root CLI parser."""
    parser = argparse.ArgumentParser(prog="twr", description="TheWriterAndReader local tools.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    config.register(subparsers)
    setup.register(subparsers)
    doctor.register(subparsers)
    write.register(subparsers)
    review.register(subparsers)
    publish.register(subparsers)
    wizard.register(subparsers)
    web.register(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
