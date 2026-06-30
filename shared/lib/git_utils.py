"""Small Git inspection helpers used by diagnostics."""
from __future__ import annotations

import subprocess
from pathlib import Path


def find_git_root(path: str | Path) -> Path | None:
    """Return the Git root for path, or None when it is not in a worktree."""
    try:
        result = subprocess.run(
            ["git", "-C", str(Path(path)), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve(strict=False)


def is_git_worktree(path: str | Path) -> bool:
    """Return True when path is inside a Git worktree."""
    return find_git_root(path) is not None


def current_branch(path: str | Path) -> str | None:
    """Return the current branch name when available."""
    try:
        result = subprocess.run(
            ["git", "-C", str(Path(path)), "branch", "--show-current"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return None
    branch = result.stdout.strip()
    return branch or None
