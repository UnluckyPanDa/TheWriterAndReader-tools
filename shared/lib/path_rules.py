"""Repository and workspace path boundary rules."""
from __future__ import annotations

from pathlib import Path

from shared.lib.safe_write import assert_inside_root


STORY_WRITE_DIRS = {
    "drafts",
    "chapters",
    "summaries",
    "handover",
    "context",
    "reviews",
    "runs",
    "snapshots",
    "state",
}


def assert_story_write_allowed(path: str | Path, story_path: str | Path) -> None:
    """Ensure story writes stay inside approved generated-output directories."""
    target = Path(path).expanduser().resolve(strict=False)
    root = Path(story_path).expanduser().resolve(strict=False)
    assert_inside_root(target, root)
    try:
        first_part = target.relative_to(root).parts[0]
    except IndexError as exc:
        raise ValueError(f"Refusing to write directly to story root: {target}") from exc
    if first_part not in STORY_WRITE_DIRS:
        raise ValueError(f"Refusing story write outside generated-output directories: {target}")


def assert_workspace_has_no_tool_code(workspace_path: str | Path) -> list[str]:
    """Return issues when a workspace contains tool-code root directories."""
    root = Path(workspace_path).expanduser().resolve(strict=False)
    issues: list[str] = []
    for name in ("tools", "cli", "shared"):
        if (root / name).exists():
            issues.append(f"workspace must not contain tool repo directory: {root / name}")
    return issues


def assert_tools_repo_has_no_story_content(tools_repo_path: str | Path) -> list[str]:
    """Return issues when active story or series roots exist in the tools repo."""
    root = Path(tools_repo_path).expanduser().resolve(strict=False)
    issues: list[str] = []
    for name in ("stories", "series"):
        if (root / name).exists():
            issues.append(f"tools repo must not contain active {name}/ directory: {root / name}")
    return issues
