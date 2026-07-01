"""CLI entrypoint for TheWriterAndReader tools."""

from __future__ import annotations

import argparse

from cli.commands import config, doctor, publish, review, wizard, write


def build_parser() -> argparse.ArgumentParser:
    """Build the root CLI parser."""
    parser = argparse.ArgumentParser(prog="twr", description="TheWriterAndReader local tools.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    config.register(subparsers)
    doctor.register(subparsers)
    write.register(subparsers)
    review.register(subparsers)
    publish.register(subparsers)
    wizard.register(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
