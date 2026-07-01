"""Writing CLI commands."""

from __future__ import annotations

import argparse


def _build_pack(args: argparse.Namespace) -> int:
    from tools.writing.build_write_pack import build_write_pack

    print(build_write_pack(args.workspace, args.story, args.chapter))
    return 0


def _generate(args: argparse.Namespace) -> int:
    from tools.writing.generate_draft import generate_draft

    print(generate_draft(args.workspace, args.story, args.chapter, args.config))
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register writing commands."""
    parser = subparsers.add_parser("write", help="Build write packs and drafts.")
    write_subparsers = parser.add_subparsers(dest="write_command", required=True)

    pack_parser = write_subparsers.add_parser("pack", help="Build context/write_pack.md.")
    pack_parser.add_argument("--workspace", required=True)
    pack_parser.add_argument("--story", required=True)
    pack_parser.add_argument("--chapter", required=True, type=int)
    pack_parser.set_defaults(handler=_build_pack)

    draft_parser = write_subparsers.add_parser("draft", help="Generate a chapter draft.")
    draft_parser.add_argument("--workspace", required=True)
    draft_parser.add_argument("--story", required=True)
    draft_parser.add_argument("--chapter", required=True, type=int)
    draft_parser.add_argument("--config", help="Optional config path.")
    draft_parser.set_defaults(handler=_generate)


def main(argv: list[str] | None = None) -> int:
    """Run writing commands directly."""
    parser = argparse.ArgumentParser(description="Writing commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register(subparsers)
    args = parser.parse_args(["write", *(argv or [])])
    return int(args.handler(args) or 0)
