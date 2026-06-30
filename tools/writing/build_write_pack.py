"""Build compact writing context packs for workspace stories."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shared.lib.safe_write import safe_write_file
from shared.lib.series_loader import load_series_pack
from shared.lib.story_loader import (
    load_markdown_file,
    load_story_canon_file,
    load_story_context_file,
    load_story_yaml,
    load_storyline_file,
)
from shared.lib.workspace_loader import resolve_series_path, resolve_story_path


def _value_as_text(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}: {_value_as_text(item)}" for key, item in value.items())
    if isinstance(value, list):
        return ", ".join(_value_as_text(item) for item in value)
    return str(value)


def _metadata_block(story_yaml: dict[str, Any]) -> str:
    if not story_yaml:
        return "- No story metadata found."
    return "\n".join(f"- {key}: {_value_as_text(value)}" for key, value in sorted(story_yaml.items()))


def _non_empty(text: str, label: str) -> str:
    stripped = text.strip()
    if stripped:
        return stripped
    return f"No {label} content was found. Add this before production drafting."


def _series_ids(story_yaml: dict[str, Any]) -> list[str]:
    raw_series = story_yaml.get("series") or story_yaml.get("series_id")
    if raw_series is None:
        return []
    if isinstance(raw_series, str):
        return [raw_series]
    if isinstance(raw_series, dict):
        series_id = raw_series.get("id") or raw_series.get("series_id")
        return [str(series_id)] if series_id else []
    if isinstance(raw_series, list):
        ids: list[str] = []
        for item in raw_series:
            if isinstance(item, str):
                ids.append(item)
            elif isinstance(item, dict):
                series_id = item.get("id") or item.get("series_id")
                if series_id:
                    ids.append(str(series_id))
        return ids
    return []


def _load_series_context(workspace_path: str | Path, story_yaml: dict[str, Any]) -> str:
    parts: list[str] = []
    for series_id in _series_ids(story_yaml):
        series_path = resolve_series_path(workspace_path, series_id)
        series_pack = load_series_pack(series_path)
        parts.append(f"### Series {series_id}\n{_non_empty(series_pack, 'series pack')}")
    return "\n\n".join(parts) if parts else "No series context is configured for this story."


def build_write_pack(
    workspace_path: str,
    story_id: str,
    chapter: int,
    options: dict[str, Any] | None = None,
) -> Path:
    """Build and write ``context/write_pack.md`` for a story chapter."""
    del options
    story_path = resolve_story_path(workspace_path, story_id)
    story_yaml = load_story_yaml(story_path)

    writer_voice = load_markdown_file(story_path / "writer" / "writer.md")
    canon = load_story_canon_file(story_path, "canon.md")
    characters = load_story_canon_file(story_path, "characters.md")
    relationships = load_story_canon_file(story_path, "relationships_and_names.md")
    locations = load_story_canon_file(story_path, "locations_objects.md")
    chapter_plan = load_storyline_file(story_path, "chapter_plan.md")
    reveal_lock = load_storyline_file(story_path, "reveal_lock.md")
    handover = load_story_context_file(story_path, "handover.md")
    series_context = _load_series_context(workspace_path, story_yaml)

    content = f"""# Write Pack

## Story Metadata
{_metadata_block(story_yaml)}

## Writer Voice
{_non_empty(writer_voice, "writer voice")}

## Current Task
- Story ID: {story_id}
- Chapter: {chapter}
- Use the chapter plan to identify the requested scene or chapter material.

## Active Canon
{_non_empty(canon, "canon")}

## Active Characters
{_non_empty(characters, "character")}

## Relationship and Name Rules
{_non_empty(relationships, "relationship and name rule")}

## Active Locations and Objects
{_non_empty(locations, "location and object")}

## Chapter Plan and Pacing
{_non_empty(chapter_plan, "chapter plan")}

## Reveal Lock
{_non_empty(reveal_lock, "reveal lock")}

## Previous Context and Handover
{_non_empty(handover, "handover")}

## Series Context
{series_context}

## Output Requirements
- Follow the story language exactly.
- Follow the writer voice and current canon.
- Do not reveal locked information.
- Do not make canon changes from the writing tool.
- Output prose suitable for review, not notes for the reviewer.
"""

    return safe_write_file(story_path / "context" / "write_pack.md", content, story_path)
