"""Writing CLI commands."""

from __future__ import annotations

import argparse


REVISION_MODES = (
    "compress",
    "deepen",
    "de-duplicate",
    "improve-dialogue",
    "strengthen-viewpoint",
    "rebalance-exposition",
    "improve-transition",
    "strengthen-hook",
    "prose-polish",
)


def _build_pack(args: argparse.Namespace) -> int:
    from tools.writing.build_write_pack import build_write_pack

    print(build_write_pack(args.workspace, args.story, args.chapter))
    return 0


def _generate(args: argparse.Namespace) -> int:
    from tools.writing.generate_draft import generate_draft

    print(generate_draft(args.workspace, args.story, args.chapter, args.config))
    return 0


def _diagnose(args: argparse.Namespace) -> int:
    from tools.writing.diagnose import write_diagnostics

    print(
        write_diagnostics(
            args.workspace,
            args.story,
            args.chapter,
            semantic_threshold=args.semantic_threshold,
            exact_min_words=args.exact_min_words,
            distinctive_min_words=args.distinctive_min_words,
        )
    )
    return 0


def _revise(args: argparse.Namespace) -> int:
    from tools.writing.revise_draft import revise_draft

    print(revise_draft(args.workspace, args.story, args.chapter, args.mode, args.config))
    return 0


def _plan_scene(args: argparse.Namespace) -> int:
    from tools.writing.scene_workflow import plan_scenes

    outputs = plan_scenes(args.workspace, args.story, args.chapter, args.config)
    print(outputs["scene_contract"])
    print(outputs["scene_skeleton"])
    return 0


def _draft_scene(args: argparse.Namespace) -> int:
    from tools.writing.scene_workflow import draft_scene

    print(draft_scene(args.workspace, args.story, args.chapter, args.scene, args.config))
    return 0


def _assemble_chapter(args: argparse.Namespace) -> int:
    from tools.writing.scene_workflow import assemble_chapter

    print(assemble_chapter(args.workspace, args.story, args.chapter))
    return 0


def _accept(args: argparse.Namespace) -> int:
    from tools.writing.accept_draft import accept_draft

    outputs = accept_draft(args.workspace, args.story, args.chapter, args.config)
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


def _revise_scene(args: argparse.Namespace) -> int:
    from tools.writing.revise_draft import revise_scene

    print(revise_scene(args.workspace, args.story, args.chapter, args.scene, args.mode, args.config))
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

    diagnose_parser = write_subparsers.add_parser("diagnose", help="Analyze repetition and source wording reuse.")
    diagnose_parser.add_argument("--workspace", required=True)
    diagnose_parser.add_argument("--story", required=True)
    diagnose_parser.add_argument("--chapter", required=True, type=int)
    diagnose_parser.add_argument("--semantic-threshold", type=float, default=0.72)
    diagnose_parser.add_argument("--exact-min-words", type=int, default=8)
    diagnose_parser.add_argument("--distinctive-min-words", type=int, default=5)
    diagnose_parser.set_defaults(handler=_diagnose)

    revise_parser = write_subparsers.add_parser("revise", help="Apply a targeted revision mode.")
    revise_parser.add_argument("--workspace", required=True)
    revise_parser.add_argument("--story", required=True)
    revise_parser.add_argument("--chapter", required=True, type=int)
    revise_parser.add_argument(
        "--mode",
        required=True,
        choices=REVISION_MODES,
    )
    revise_parser.add_argument("--config", help="Optional config path.")
    revise_parser.set_defaults(handler=_revise)

    plan_parser = write_subparsers.add_parser("plan-scene", help="Build a validated scene contract and skeleton.")
    plan_parser.add_argument("--workspace", required=True)
    plan_parser.add_argument("--story", required=True)
    plan_parser.add_argument("--chapter", required=True, type=int)
    plan_parser.add_argument("--config", help="Optional config path.")
    plan_parser.set_defaults(handler=_plan_scene)

    scene_parser = write_subparsers.add_parser("draft-scene", help="Draft one scene from the active scene plan.")
    scene_parser.add_argument("--workspace", required=True)
    scene_parser.add_argument("--story", required=True)
    scene_parser.add_argument("--chapter", required=True, type=int)
    scene_parser.add_argument("--scene", required=True)
    scene_parser.add_argument("--config", help="Optional config path.")
    scene_parser.set_defaults(handler=_draft_scene)

    assemble_parser = write_subparsers.add_parser("assemble-chapter", help="Assemble planned scene drafts in order.")
    assemble_parser.add_argument("--workspace", required=True)
    assemble_parser.add_argument("--story", required=True)
    assemble_parser.add_argument("--chapter", required=True, type=int)
    assemble_parser.set_defaults(handler=_assemble_chapter)

    accept_parser = write_subparsers.add_parser(
        "accept",
        help="Promote a gate-approved draft and update summary, handover, and state.",
    )
    accept_parser.add_argument("--workspace", required=True)
    accept_parser.add_argument("--story", required=True)
    accept_parser.add_argument("--chapter", required=True, type=int)
    accept_parser.add_argument("--config", help="Optional config path.")
    accept_parser.set_defaults(handler=_accept)

    revise_scene_parser = write_subparsers.add_parser(
        "revise-scene",
        help="Apply a targeted revision to one active scene draft.",
    )
    revise_scene_parser.add_argument("--workspace", required=True)
    revise_scene_parser.add_argument("--story", required=True)
    revise_scene_parser.add_argument("--chapter", required=True, type=int)
    revise_scene_parser.add_argument("--scene", required=True)
    revise_scene_parser.add_argument("--mode", required=True, choices=REVISION_MODES)
    revise_scene_parser.add_argument("--config", help="Optional config path.")
    revise_scene_parser.set_defaults(handler=_revise_scene)


def main(argv: list[str] | None = None) -> int:
    """Run writing commands directly."""
    parser = argparse.ArgumentParser(description="Writing commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register(subparsers)
    args = parser.parse_args(["write", *(argv or [])])
    return int(args.handler(args) or 0)
