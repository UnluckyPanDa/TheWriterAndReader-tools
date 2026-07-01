"""Load story metadata and story-local Markdown context files."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from shared.lib.yaml_utils import load_yaml_text


def load_story_yaml(story_path: str | Path) -> dict:
    """Load story.yaml from a story directory."""
    path = Path(story_path).expanduser().resolve(strict=False) / "story.yaml"
    if not path.exists():
        raise FileNotFoundError(f"story.yaml not found: {path}")
    data = load_yaml_text(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"story.yaml must contain a mapping: {path}")
    return data


def load_story_paths(story_path: str | Path) -> dict:
    """Return common story subpaths."""
    root = Path(story_path).expanduser().resolve(strict=False)
    return {
        "root": root,
        "canon": root / "canon",
        "writer": root / "writer",
        "storyline": root / "storyline",
        "context": root / "context",
        "reviewers": root / "reviewers",
        "drafts": root / "drafts",
        "chapters": root / "chapters",
        "reviews": root / "reviews",
        "state": root / "state",
    }


def load_markdown_file(path: str | Path, default: str = "") -> str:
    """Load a Markdown file, returning default when absent."""
    markdown_path = Path(path).expanduser().resolve(strict=False)
    if not markdown_path.exists():
        return default
    return markdown_path.read_text(encoding="utf-8")


def load_story_context_file(story_path: str | Path, name: str) -> str:
    """Load a file from the story context directory."""
    return load_markdown_file(Path(story_path) / "context" / name)


def load_story_canon_file(story_path: str | Path, name: str) -> str:
    """Load a file from the story canon directory."""
    return load_markdown_file(Path(story_path) / "canon" / name)


def load_storyline_file(story_path: str | Path, name: str) -> str:
    """Load a file from the story storyline directory."""
    return load_markdown_file(Path(story_path) / "storyline" / name)


def load_story(story_path: str | Path) -> dict[str, Any]:
    """Load story metadata and key paths."""
    return {
        "path": str(Path(story_path).expanduser().resolve(strict=False)),
        "story": load_story_yaml(story_path),
        "paths": load_story_paths(story_path),
    }
