"""Story wizard CLI commands."""

from __future__ import annotations

import argparse


def _workspace_init(args: argparse.Namespace) -> int:
    from tools.wizard.scaffold import init_workspace

    print(init_workspace(args.workspace, args.workspace_id))
    return 0


def _story_add(args: argparse.Namespace) -> int:
    from tools.wizard.scaffold import add_story

    print(add_story(args.workspace, args.story, args.title, args.language))
    return 0


def _series_add(args: argparse.Namespace) -> int:
    from tools.wizard.scaffold import add_series

    print(add_series(args.workspace, args.series, args.title))
    return 0


def _relation_plot_init(args: argparse.Namespace) -> int:
    from tools.wizard.relation_plot import init_relation_plot

    print(init_relation_plot(args.workspace, args.story))
    return 0


def _relation_plot_build(args: argparse.Namespace) -> int:
    from tools.wizard.relation_plot import build_relation_plot

    print(build_relation_plot(args.workspace, args.story))
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register wizard command."""
    parser = subparsers.add_parser("wizard", help="Story wizard commands.")
    wizard_subparsers = parser.add_subparsers(dest="wizard_command", required=True)

    workspace_parser = wizard_subparsers.add_parser("workspace", help="Create workspace scaffolds.")
    workspace_subparsers = workspace_parser.add_subparsers(dest="workspace_command", required=True)
    init_parser = workspace_subparsers.add_parser("init", help="Create workspace.yaml.")
    init_parser.add_argument("--workspace", required=True)
    init_parser.add_argument("--workspace-id", required=True)
    init_parser.set_defaults(handler=_workspace_init)

    story_parser = wizard_subparsers.add_parser("story", help="Create story scaffolds.")
    story_subparsers = story_parser.add_subparsers(dest="story_command", required=True)
    add_story_parser = story_subparsers.add_parser("add", help="Add a story from the bundled template.")
    add_story_parser.add_argument("--workspace", required=True)
    add_story_parser.add_argument("--story", required=True)
    add_story_parser.add_argument("--title", required=True)
    add_story_parser.add_argument("--language", required=True)
    add_story_parser.set_defaults(handler=_story_add)

    series_parser = wizard_subparsers.add_parser("series", help="Create series scaffolds.")
    series_subparsers = series_parser.add_subparsers(dest="series_command", required=True)
    add_series_parser = series_subparsers.add_parser("add", help="Add a series from the bundled template.")
    add_series_parser.add_argument("--workspace", required=True)
    add_series_parser.add_argument("--series", required=True)
    add_series_parser.add_argument("--title", required=True)
    add_series_parser.set_defaults(handler=_series_add)

    relation_parser = wizard_subparsers.add_parser(
        "relation-plot", help="Initialize or build a local 3D relationship plot."
    )
    relation_subparsers = relation_parser.add_subparsers(dest="relation_plot_command", required=True)
    relation_init_parser = relation_subparsers.add_parser(
        "init", help="Add an empty relationship graph to an existing story."
    )
    relation_init_parser.add_argument("--workspace", required=True)
    relation_init_parser.add_argument("--story", required=True)
    relation_init_parser.set_defaults(handler=_relation_plot_init)

    relation_build_parser = relation_subparsers.add_parser(
        "build", help="Build the story's standalone 3D relationship plot."
    )
    relation_build_parser.add_argument("--workspace", required=True)
    relation_build_parser.add_argument("--story", required=True)
    relation_build_parser.set_defaults(handler=_relation_plot_build)


def main(argv: list[str] | None = None) -> int:
    """Run wizard directly."""
    parser = argparse.ArgumentParser(description="Wizard command.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register(subparsers)
    args = parser.parse_args(["wizard", *(argv or [])])
    return int(args.handler(args) or 0)
