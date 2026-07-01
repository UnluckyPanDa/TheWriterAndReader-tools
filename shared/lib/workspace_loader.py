"""Load and validate external story workspaces."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from shared.lib.safe_write import assert_inside_root
from shared.lib.yaml_utils import load_yaml_text


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required YAML file not found: {path}")
    data = load_yaml_text(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping: {path}")
    return data


def load_workspace_yaml(workspace_path: str | Path) -> dict:
    """Load workspace.yaml from a workspace directory."""
    root = Path(workspace_path).expanduser().resolve(strict=False)
    return _read_yaml(root / "workspace.yaml")


def validate_workspace_path(workspace_path: str | Path) -> list[str]:
    """Return validation messages for a workspace path."""
    root = Path(workspace_path).expanduser().resolve(strict=False)
    issues: list[str] = []
    if not root.exists():
        issues.append(f"workspace path does not exist: {root}")
    if not root.is_dir():
        issues.append(f"workspace path is not a directory: {root}")
    if not (root / "workspace.yaml").exists():
        issues.append(f"workspace.yaml missing: {root / 'workspace.yaml'}")
    return issues


def _entry_path(entries: Any, entry_id: str, default: str) -> str:
    if isinstance(entries, dict):
        value = entries.get(entry_id)
        if isinstance(value, dict):
            return str(value.get("path", default))
        if isinstance(value, str):
            return value
    if isinstance(entries, list):
        for item in entries:
            if isinstance(item, dict) and item.get("id") == entry_id:
                return str(item.get("path", default))
            if item == entry_id:
                return default
    return default


def resolve_story_path(workspace_path: str | Path, story_id: str) -> Path:
    """Resolve a story id to a directory inside the workspace."""
    root = Path(workspace_path).expanduser().resolve(strict=False)
    config = load_workspace_yaml(root)
    relative = _entry_path(config.get("stories"), story_id, f"stories/{story_id}")
    path = (root / relative).resolve(strict=False)
    assert_inside_root(path, root)
    if not (path / "story.yaml").exists():
        raise FileNotFoundError(f"story.yaml not found for story '{story_id}' at {path}")
    return path


def resolve_series_path(workspace_path: str | Path, series_id: str) -> Path:
    """Resolve a series id to a directory inside the workspace."""
    root = Path(workspace_path).expanduser().resolve(strict=False)
    config = load_workspace_yaml(root)
    relative = _entry_path(config.get("series"), series_id, f"series/{series_id}")
    path = (root / relative).resolve(strict=False)
    assert_inside_root(path, root)
    if not (path / "series.yaml").exists():
        raise FileNotFoundError(f"series.yaml not found for series '{series_id}' at {path}")
    return path


def list_stories(workspace_path: str | Path) -> list[str]:
    """List story ids in a workspace."""
    root = Path(workspace_path).expanduser().resolve(strict=False)
    stories_root = root / "stories"
    if not stories_root.exists():
        return []
    return sorted(path.name for path in stories_root.iterdir() if path.is_dir() and (path / "story.yaml").exists())


def list_series(workspace_path: str | Path) -> list[str]:
    """List series ids in a workspace."""
    root = Path(workspace_path).expanduser().resolve(strict=False)
    series_root = root / "series"
    if not series_root.exists():
        return []
    return sorted(path.name for path in series_root.iterdir() if path.is_dir() and (path / "series.yaml").exists())


def load_workspace(workspace_path: str | Path) -> dict:
    """Load a workspace with discovered story and series ids."""
    issues = validate_workspace_path(workspace_path)
    if issues:
        raise ValueError("Invalid workspace:\n" + "\n".join(issues))
    root = Path(workspace_path).expanduser().resolve(strict=False)
    return {
        "path": str(root),
        "workspace": load_workspace_yaml(root),
        "stories": list_stories(root),
        "series": list_series(root),
    }
