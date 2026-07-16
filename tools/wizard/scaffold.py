"""Scaffold external workspaces, stories, and series from bundled templates."""

from __future__ import annotations

from pathlib import Path

from shared.lib.safe_write import assert_inside_root, safe_copy_file, safe_mkdir, safe_write_file
from shared.lib.workspace_loader import validate_workspace_path
from shared.lib.yaml_utils import dump_yaml, load_yaml_text


TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates"


def init_workspace(workspace: str | Path, workspace_id: str) -> Path:
    """Create a new workspace.yaml in an external workspace directory."""
    root = Path(workspace).expanduser().resolve(strict=False)
    safe_mkdir(root, root)
    config_path = root / "workspace.yaml"
    if config_path.exists():
        raise FileExistsError(f"workspace.yaml already exists: {config_path}")
    data = {"workspace_id": workspace_id, "stories": {}, "series": {}}
    return safe_write_file(config_path, dump_yaml(data, sort_keys=False), root)


def add_story(workspace: str | Path, story_id: str, title: str, language: str) -> Path:
    """Add a story scaffold to an existing workspace."""
    root = _validated_workspace_root(workspace)
    workspace_yaml = _load_workspace_yaml(root)
    stories = _entry_mapping(workspace_yaml, "stories")
    if story_id in stories:
        raise FileExistsError(f"story already exists in workspace.yaml: {story_id}")

    relative = Path("stories") / story_id
    story_path = root / relative
    _copy_template_tree(TEMPLATE_ROOT / "story-template", story_path, root)

    story_yaml = _load_yaml_file(story_path / "story.yaml")
    story_yaml["id"] = story_id
    story_yaml["title"] = title
    story_yaml["language"] = {"primary": language, "allowed": [language], "forbidden": []}
    safe_write_file(story_path / "story.yaml", dump_yaml(story_yaml, sort_keys=False), root)

    stories[story_id] = {"path": relative.as_posix()}
    workspace_yaml["stories"] = stories
    safe_write_file(root / "workspace.yaml", dump_yaml(workspace_yaml, sort_keys=False), root)
    return story_path


def add_series(workspace: str | Path, series_id: str, title: str) -> Path:
    """Add a series scaffold to an existing workspace."""
    root = _validated_workspace_root(workspace)
    workspace_yaml = _load_workspace_yaml(root)
    series = _entry_mapping(workspace_yaml, "series")
    if series_id in series:
        raise FileExistsError(f"series already exists in workspace.yaml: {series_id}")

    relative = Path("series") / series_id
    series_path = root / relative
    _copy_template_tree(TEMPLATE_ROOT / "series-template", series_path, root)

    series_yaml = _load_yaml_file(series_path / "series.yaml")
    series_yaml["id"] = series_id
    series_yaml["title"] = title
    safe_write_file(series_path / "series.yaml", dump_yaml(series_yaml, sort_keys=False), root)

    series[series_id] = {"path": relative.as_posix()}
    workspace_yaml["series"] = series
    safe_write_file(root / "workspace.yaml", dump_yaml(workspace_yaml, sort_keys=False), root)
    return series_path


def _validated_workspace_root(workspace: str | Path) -> Path:
    root = Path(workspace).expanduser().resolve(strict=False)
    issues = validate_workspace_path(root)
    if issues:
        raise ValueError("Invalid workspace:\n" + "\n".join(issues))
    return root


def _load_workspace_yaml(root: Path) -> dict:
    return _load_yaml_file(root / "workspace.yaml")


def _load_yaml_file(path: Path) -> dict:
    data = load_yaml_text(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping: {path}")
    return data


def _entry_mapping(data: dict, key: str) -> dict:
    value = data.get(key)
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        mapped = {}
        for item in value:
            if isinstance(item, str):
                mapped[item] = {"path": f"{key}/{item}"}
            elif isinstance(item, dict) and item.get("id"):
                mapped[str(item["id"])] = {"path": item.get("path", f"{key}/{item['id']}")}
        return mapped
    raise ValueError(f"workspace.yaml field must be a mapping or list: {key}")


def _copy_template_tree(template_root: Path, target_root: Path, allowed_root: Path) -> None:
    if target_root.exists():
        raise FileExistsError(f"target already exists: {target_root}")
    assert_inside_root(target_root, allowed_root)
    for source in sorted(template_root.rglob("*")):
        relative = source.relative_to(template_root)
        target = target_root / relative
        if source.is_dir():
            safe_mkdir(target, allowed_root)
        else:
            safe_copy_file(source, target, allowed_root)
