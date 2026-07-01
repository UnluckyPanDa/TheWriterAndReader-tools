"""Build publish context packs for workspace stories."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.safe_write import safe_write_file
from shared.lib.story_loader import load_markdown_file, load_story_yaml
from shared.lib.workspace_loader import resolve_story_path


def _language(story_yaml: dict[str, Any]) -> str:
    raw = story_yaml.get("language")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, dict) and isinstance(raw.get("primary"), str):
        return raw["primary"].strip() or "en"
    return "en"


def _chapter_source(story_path: Path, chapter: int) -> tuple[str, str]:
    accepted = story_path / "chapters" / f"chapter_{chapter:03d}.md"
    if accepted.exists():
        return "accepted", accepted.read_text(encoding="utf-8")
    draft = story_path / "drafts" / f"chapter_{chapter:03d}.md"
    if draft.exists():
        return "draft", draft.read_text(encoding="utf-8")
    return "missing", ""


def _gate_status_text(story_path: Path, chapter: int) -> str:
    return load_markdown_file(story_path / "reviews" / f"chapter_{chapter:03d}" / "review_gate_status.md")


def _source_warning(source_type: str, gate_status: str) -> str:
    if source_type == "accepted":
        return "No publish source warning."
    if source_type == "draft":
        if "Gate Status: accepted" in gate_status:
            return "Draft source has an accepted review gate but has not been copied to chapters/."
        return "Draft source is not accepted for final publishing."
    return "No chapter source was found."


def build_publish_pack(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    options: dict[str, Any] | None = None,
) -> Path:
    """Build and write ``context/publish_pack.md`` for a chapter."""
    del options
    story_path = resolve_story_path(workspace_path, story_id)
    story_yaml = load_story_yaml(story_path)
    source_type, chapter_text = _chapter_source(story_path, chapter)
    gate_status = _gate_status_text(story_path, chapter)
    title = str(story_yaml.get("title") or story_id)
    language = _language(story_yaml)
    warning = _source_warning(source_type, gate_status)

    content = f"""# Publish Pack

## Story Metadata
- Story ID: {story_id}
- Title: {title}
- Language: {language}
- Chapter: {chapter}

## Publish Readiness
- Source Type: {source_type}
- Warning: {warning}

## Review Gate
{gate_status.strip() or "No review gate status was found."}

## Chapter Source
{chapter_text.strip() or "No chapter text was found."}

## Publish Rules
- Publish only accepted chapter text from `chapters/` unless the user explicitly overrides.
- Do not include review notes, hidden canon, handover notes, or model metadata in final output.
- Do not edit canon or source chapter files from publish tools.
"""

    output_path = story_path / "context" / "publish_pack.md"
    assert_story_write_allowed(output_path, story_path)
    return safe_write_file(output_path, content, story_path)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for direct module execution."""
    parser = argparse.ArgumentParser(description="Build a publish pack.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--story", required=True)
    parser.add_argument("--chapter", required=True, type=int)
    args = parser.parse_args(argv)
    print(build_publish_pack(args.workspace, args.story, args.chapter))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
