"""Publish CLI commands."""

from __future__ import annotations

import argparse


def _build_pack(args: argparse.Namespace) -> int:
    from tools.publish.build_publish_pack import build_publish_pack

    print(build_publish_pack(args.workspace, args.story, args.chapter))
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register publish commands."""
    parser = subparsers.add_parser("publish", help="Build publish context.")
    publish_subparsers = parser.add_subparsers(dest="publish_command", required=True)

    pack_parser = publish_subparsers.add_parser("pack", help="Build context/publish_pack.md.")
    pack_parser.add_argument("--workspace", required=True)
    pack_parser.add_argument("--story", required=True)
    pack_parser.add_argument("--chapter", required=True, type=int)
    pack_parser.set_defaults(handler=_build_pack)


def main(argv: list[str] | None = None) -> int:
    """Run publish commands directly."""
    parser = argparse.ArgumentParser(description="Publish commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register(subparsers)
    args = parser.parse_args(["publish", *(argv or [])])
    return int(args.handler(args) or 0)
