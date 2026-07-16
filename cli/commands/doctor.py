"""Doctor CLI command."""

from __future__ import annotations

import argparse
from pathlib import Path

TOOLS_REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(args: argparse.Namespace) -> int:
    from shared.lib.config_loader import load_config, validate_config
    from shared.lib.path_rules import assert_tools_repo_has_no_story_content, assert_workspace_has_no_tool_code
    from shared.lib.workspace_loader import validate_workspace_path

    issues = []
    issues.extend(validate_config(load_config(args.config)))
    issues.extend(assert_tools_repo_has_no_story_content(TOOLS_REPO_ROOT))
    if args.workspace:
        issues.extend(validate_workspace_path(args.workspace))
        issues.extend(assert_workspace_has_no_tool_code(args.workspace))

    if issues:
        for issue in issues:
            print(f"error: {issue}")
        return 1
    print("doctor ok")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register doctor command."""
    parser = subparsers.add_parser("doctor", help="Validate config and path boundaries.")
    parser.add_argument("--config", help="Optional config path.")
    parser.add_argument("--workspace", help="Optional external story workspace path.")
    parser.set_defaults(handler=_run)


def main(argv: list[str] | None = None) -> int:
    """Run doctor directly."""
    parser = argparse.ArgumentParser(description="Doctor command.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register(subparsers)
    args = parser.parse_args(["doctor", *(argv or [])])
    return int(args.handler(args) or 0)
