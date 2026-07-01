"""Review CLI commands."""

from __future__ import annotations

import argparse


def _build_pack(args: argparse.Namespace) -> int:
    from tools.review.build_review_pack import build_review_pack

    print(build_review_pack(args.workspace, args.story, args.chapter))
    return 0


def _run(args: argparse.Namespace) -> int:
    from tools.review.run_review import run_review

    outputs = run_review(args.workspace, args.story, args.chapter, args.config)
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register review commands."""
    parser = subparsers.add_parser("review", help="Build review packs and run reviewers.")
    review_subparsers = parser.add_subparsers(dest="review_command", required=True)

    pack_parser = review_subparsers.add_parser("pack", help="Build context/review_pack.md.")
    pack_parser.add_argument("--workspace", required=True)
    pack_parser.add_argument("--story", required=True)
    pack_parser.add_argument("--chapter", required=True, type=int)
    pack_parser.set_defaults(handler=_build_pack)

    run_parser = review_subparsers.add_parser("run", help="Run configured reviewers.")
    run_parser.add_argument("--workspace", required=True)
    run_parser.add_argument("--story", required=True)
    run_parser.add_argument("--chapter", required=True, type=int)
    run_parser.add_argument("--config", help="Optional config path.")
    run_parser.set_defaults(handler=_run)


def main(argv: list[str] | None = None) -> int:
    """Run review commands directly."""
    parser = argparse.ArgumentParser(description="Review commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register(subparsers)
    args = parser.parse_args(["review", *(argv or [])])
    return int(args.handler(args) or 0)
