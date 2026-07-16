"""Build compact review context packs for workspace stories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from shared.lib.chapter_context import load_chapter_inputs
from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.safe_write import safe_write_file
from shared.lib.story_loader import load_markdown_file, load_story_context_file, load_story_yaml
from shared.lib.workspace_loader import resolve_story_path
from tools.writing.build_write_pack import build_write_pack
from tools.writing.diagnose import write_diagnostics


def _generation_artifact(story_path: Path, chapter: int, key: str) -> str:
    provenance_path = story_path / "runs" / f"chapter_{chapter:03d}_generation.json"
    fallback_path = story_path / "context" / f"chapter_{chapter:03d}_{key}.json"
    if not provenance_path.exists():
        return _required_text(load_markdown_file(fallback_path), key.replace("_", " "))
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        relative = provenance.get("outputs", {}).get(key)
        if not isinstance(relative, str):
            return _required_text(load_markdown_file(fallback_path), key.replace("_", " "))
        return _required_text(load_markdown_file(story_path / relative), key.replace("_", " "))
    except (json.JSONDecodeError, OSError, ValueError):
        return _required_text(load_markdown_file(fallback_path), key.replace("_", " "))


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


def _required_text(text: str, label: str) -> str:
    return text.strip() or f"No {label} content was found."


def build_review_pack(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    options: dict[str, Any] | None = None,
) -> Path:
    """Build and write ``context/review_pack.md`` for a story chapter."""
    del options
    story_path = resolve_story_path(workspace_path, story_id)
    story_yaml = load_story_yaml(story_path)
    draft_path = story_path / "drafts" / f"chapter_{chapter:03d}.md"
    draft = load_markdown_file(draft_path)
    build_write_pack(str(workspace_path), story_id, chapter)
    write_pack = load_story_context_file(story_path, "write_pack.md")
    reveal_lock = load_markdown_file(story_path / "storyline" / "reveal_lock.md")
    reviewer_config = load_markdown_file(story_path / "reviewers" / "reviewer_config.yaml")
    chapter_inputs = load_chapter_inputs(story_path, chapter)
    if draft.strip():
        diagnostics_path = write_diagnostics(workspace_path, story_id, chapter)
        diagnostics = diagnostics_path.read_text(encoding="utf-8")
    else:
        diagnostics = "No draft diagnostics are available."
    scene_contract = _generation_artifact(story_path, chapter, "scene_contract")
    scene_skeleton = _generation_artifact(story_path, chapter, "scene_skeleton")

    content = f"""# Review Pack

## Story Metadata
{_metadata_block(story_yaml)}

## Current Task
- Story ID: {story_id}
- Chapter: {chapter}
- Draft File: drafts/chapter_{chapter:03d}.md

## Draft Under Review
{_required_text(draft, "draft")}

## Active Chapter Brief
{chapter_inputs["brief"]}

## Active Chapter Context
{chapter_inputs["context"]}

## Active Chapter Generation Instruction
{chapter_inputs["instruction"]}

## Previous Accepted Review Handoff
{chapter_inputs["previous_handoff"]}

## Validated Scene Contract
{scene_contract}

## Validated Scene Skeleton
{scene_skeleton}

## Deterministic Writing Diagnostics
{diagnostics}

## Write Pack Reference
{_required_text(write_pack, "write pack")}

## Reveal Lock
{_required_text(reveal_lock, "reveal lock")}

## Reviewer Configuration
{_required_text(reviewer_config, "reviewer configuration")}

## Review Requirements
- Review the draft against the supplied story context.
- Identify blocker and major issues before minor polish.
- Evaluate novel quality as well as continuity: scene dramatization, causal pressure, close point of view, character choice, prose precision, and ending impact.
- Evaluate local pacing, scene pacing, and chapter pacing separately using the complete draft and scene plan.
- Treat exact source-wording flags as revision targets unless the phrase is a required fixed term or common name.
- Every issue must cite a specific scene, paragraph, or short quotation and explain why it affects the reader.
- A pass must be based on the supplied text. Do not issue a generic approval.
- Do not edit canon or draft files.
- Use the standard review report shape.
- Include clear gate guidance: accept, revise, or block.
"""

    output_path = story_path / "context" / "review_pack.md"
    assert_story_write_allowed(output_path, story_path)
    return safe_write_file(output_path, content, story_path)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for direct module execution."""
    parser = argparse.ArgumentParser(description="Build a review pack.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--story", required=True)
    parser.add_argument("--chapter", required=True, type=int)
    args = parser.parse_args(argv)
    print(build_review_pack(args.workspace, args.story, args.chapter))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
