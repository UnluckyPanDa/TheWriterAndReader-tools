"""Build compact writing context packs for workspace stories."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shared.lib.chapter_context import load_chapter_inputs
from shared.lib.relationship_graph import relationship_graph_summary
from shared.lib.safe_write import assert_inside_root, safe_write_file
from shared.lib.series_loader import load_series_pack
from shared.lib.story_loader import (
    load_markdown_file,
    load_story_canon_file,
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


def _writer_profile_path(story_path: Path, story_yaml: dict[str, Any]) -> Path:
    writer = story_yaml.get("writer", {})
    configured = writer.get("profile") if isinstance(writer, dict) else None
    relative = configured if isinstance(configured, str) and configured.strip() else "writer/writer.md"
    profile_path = (story_path / relative).resolve(strict=False)
    assert_inside_root(profile_path, story_path)
    return profile_path


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

    writer_voice = load_markdown_file(_writer_profile_path(story_path, story_yaml))
    canon = load_story_canon_file(story_path, "canon.md")
    characters = load_story_canon_file(story_path, "characters.md")
    relationships = load_story_canon_file(story_path, "relationships_and_names.md")
    relationship_summary = relationship_graph_summary(story_path, chapter)
    locations = load_story_canon_file(story_path, "locations_objects.md")
    reveal_lock = load_storyline_file(story_path, "reveal_lock.md")
    chapter_inputs = load_chapter_inputs(story_path, chapter)
    chapter_plan = load_storyline_file(story_path, "chapter_plan.md")
    series_context = _load_series_context(workspace_path, story_yaml)
    legacy_plan = (
        _non_empty(chapter_plan, "chapter plan")
        if chapter_inputs["has_active_direction"] == "no"
        else "Not loaded because active chapter-specific direction is available."
    )

    content = f"""# Write Pack

## Story Metadata
{_metadata_block(story_yaml)}

## Writer Voice [VOICE]
{_non_empty(writer_voice, "writer voice")}

## Current Task
- Story ID: {story_id}
- Chapter: {chapter}
- Active chapter direction found: {chapter_inputs["has_active_direction"]}.

## Active Chapter Brief [BEAT]
{chapter_inputs["brief"]}

## Active Chapter Context [REFERENCE]
{chapter_inputs["context"]}

## Active Chapter Generation Instruction [BEAT]
{chapter_inputs["instruction"]}

## Previous Accepted Review Handoff [SOURCE_TEXT]
{chapter_inputs["previous_handoff"]}

## Active Canon [FACT]
{_non_empty(canon, "canon")}

## Canon Usage Contract [CONSTRAINT]
- Canon is private factual reference, not source prose or a vocabulary list.
- Use canon only to determine what is true, what the viewpoint character knows, what they want, what cannot happen, and what must remain unrevealed.
- Do not copy, paraphrase, explain, or repeatedly echo canon wording in narration.
- Include a canon fact in the chapter only when a character encounters its concrete consequence.
- Prioritize the current chapter objective, character desire and resistance, concrete action, and consequence over wider background.

## Active Characters [FACT]
{_non_empty(characters, "character")}

## Relationship and Name Rules [CONSTRAINT]
{_non_empty(relationships, "relationship and name rule")}

## Chapter-Visible Relationship Graph [FACT]
{relationship_summary}

## Active Locations and Objects [FACT]
{_non_empty(locations, "location and object")}

## Chapter Plan and Pacing [REFERENCE]
{legacy_plan}

## Reveal Lock [FORBIDDEN]
{_non_empty(reveal_lock, "reveal lock")}

## Previous Context and Handover [REFERENCE]
{chapter_inputs["global_handover"]}

## Series Context [FACT]
{series_context}

## Output Requirements
- Follow the story language exactly.
- Follow the writer voice and current canon.
- Do not reveal locked information.
- Do not make canon changes from the writing tool.
- Write a complete chapter, not a plot summary or an outline.
- Give each scene a concrete immediate objective, pressure or obstacle, a character choice, and a visible consequence or turn.
- Dramatize pivotal information through action, dialogue, setting, and close point of view; use exposition only when it actively changes the scene.
- Write a sequence of lived events, not an illustrated summary of the supplied canon.
- Reveal characterization through choices, omissions, interruptions, and specific physical behavior; do not label traits or themes in narration.
- Keep dialogue goal-directed and socially constrained. Do not use dialogue to deliver canon or explain the plot to the reader.
- Remove abstract emotional explanations, repeated meanings, generic reactions, and planning-language terminology before returning the draft.
- Begin inside an active situation with immediate pressure and a specific detail that does not fit. End after a concrete discovery, choice, interruption, or changed relationship.
- Keep emotional movement in the characters' choices and reactions. Do not end by restating the chapter's theme or plot in abstract narration.
- Before returning the draft, revise for scene continuity, specific sensory detail, varied sentence rhythm, and avoidable repetition.
"""

    return safe_write_file(story_path / "context" / "write_pack.md", content, story_path)
