"""Review CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path


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


def _prepare(args: argparse.Namespace) -> int:
    from shared.lib.review_handoff import prepare_review_handoff

    print(prepare_review_handoff(args.workspace, args.story, args.chapter))
    return 0


def _execute(args: argparse.Namespace) -> int:
    from shared.lib.review_handoff import execute_review_handoff

    print(execute_review_handoff(args.workspace, args.story, args.chapter, args.request, args.config))
    return 0


def _apply(args: argparse.Namespace) -> int:
    from shared.lib.review_handoff import apply_review_handoff

    outputs = apply_review_handoff(args.workspace, args.story, args.chapter, args.request, args.result)
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


def _novelness(args: argparse.Namespace) -> int:
    from tools.review.run_review import run_novelness_gate

    print(run_novelness_gate(args.workspace, args.story, args.chapter))
    return 0


def _rereview(args: argparse.Namespace) -> int:
    from tools.review.rereview import rereview_explanation

    explanation = args.explanation
    if args.explanation_file:
        explanation = Path(args.explanation_file).expanduser().read_text(encoding="utf-8")
    outputs = rereview_explanation(
        args.workspace,
        args.story,
        args.chapter,
        args.reviewer,
        explanation,
        args.config,
        args.layer,
    )
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

    prepare_parser = review_subparsers.add_parser(
        "prepare",
        help="Prepare an append-only review request for another thread or device.",
    )
    prepare_parser.add_argument("--workspace", required=True)
    prepare_parser.add_argument("--story", required=True)
    prepare_parser.add_argument("--chapter", required=True, type=int)
    prepare_parser.set_defaults(handler=_prepare)

    execute_parser = review_subparsers.add_parser(
        "execute",
        help="Execute a prepared review request without promoting current records.",
    )
    execute_parser.add_argument("--workspace", required=True)
    execute_parser.add_argument("--story", required=True)
    execute_parser.add_argument("--chapter", required=True, type=int)
    execute_parser.add_argument("--request", required=True)
    execute_parser.add_argument("--config", help="Optional config path.")
    execute_parser.set_defaults(handler=_execute)

    apply_parser = review_subparsers.add_parser(
        "apply",
        help="Validate and apply a complete review handoff result.",
    )
    apply_parser.add_argument("--workspace", required=True)
    apply_parser.add_argument("--story", required=True)
    apply_parser.add_argument("--chapter", required=True, type=int)
    apply_parser.add_argument("--request", required=True)
    apply_parser.add_argument("--result", required=True)
    apply_parser.set_defaults(handler=_apply)

    novelness_parser = review_subparsers.add_parser(
        "novelness",
        help="Rebuild the Novelness Gate from current reports and diagnostics.",
    )
    novelness_parser.add_argument("--workspace", required=True)
    novelness_parser.add_argument("--story", required=True)
    novelness_parser.add_argument("--chapter", required=True, type=int)
    novelness_parser.set_defaults(handler=_novelness)

    rereview_parser = review_subparsers.add_parser(
        "rereview",
        help="Run the one-time higher-intelligence review of a writer explanation.",
    )
    rereview_parser.add_argument("--workspace", required=True)
    rereview_parser.add_argument("--story", required=True)
    rereview_parser.add_argument("--chapter", required=True, type=int)
    rereview_parser.add_argument("--reviewer", required=True)
    rereview_parser.add_argument("--layer", choices=("standard", "series", "special"), default="standard")
    explanation_group = rereview_parser.add_mutually_exclusive_group(required=True)
    explanation_group.add_argument("--explanation")
    explanation_group.add_argument("--explanation-file")
    rereview_parser.add_argument("--config", help="Optional config path.")
    rereview_parser.set_defaults(handler=_rereview)


def main(argv: list[str] | None = None) -> int:
    """Run review commands directly."""
    parser = argparse.ArgumentParser(description="Review commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register(subparsers)
    args = parser.parse_args(["review", *(argv or [])])
    return int(args.handler(args) or 0)
