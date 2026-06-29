from __future__ import annotations

import argparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_text_if_exists(path: Path, default: str = "") -> str:
    return path.read_text(encoding="utf-8") if path.exists() else default


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def resolve_story_root(story: str | Path, repo_root: Path = REPO_ROOT) -> Path:
    story_path = Path(story).expanduser()
    stories_root = (repo_root / "stories").resolve(strict=False)
    if story_path.is_absolute():
        candidate = story_path.resolve(strict=False)
    elif len(story_path.parts) > 1:
        candidate = (repo_root / story_path).resolve(strict=False)
    else:
        candidate = (stories_root / story_path).resolve(strict=False)

    try:
        candidate.relative_to(stories_root)
    except ValueError as exc:
        raise ValueError(f"Story path must stay under {stories_root}: {story}") from exc
    return candidate


def assert_write_inside_story_root(path: Path, story_root: Path) -> None:
    resolved_path = path.resolve(strict=False)
    resolved_root = story_root.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Refusing to write outside story root {resolved_root}: {resolved_path}") from exc


def story_dir(story_id: str, repo_root: Path = REPO_ROOT) -> Path:
    return resolve_story_root(story_id, repo_root)


def build_context_packet(story_id: str, chapter_number: int, repo_root: Path = REPO_ROOT) -> Path:
    base = story_dir(story_id, repo_root)
    if not base.exists():
        raise FileNotFoundError(f"Story not found: {story_id}")

    chapter = f"{chapter_number:03d}"
    previous = f"{chapter_number - 1:03d}"
    summaries_dir = base / "summaries"
    assert_write_inside_story_root(summaries_dir, base)
    summaries_dir.mkdir(parents=True, exist_ok=True)

    story_config_path = _first_existing([base / "story.yaml", base / "story_config.yaml"])
    story_config = (
        read_text_if_exists(story_config_path, "(missing story.yaml or story_config.yaml)")
        if story_config_path
        else "(missing story.yaml or story_config.yaml)"
    )
    canon_dir = base / "canon"
    world = read_text_if_exists(canon_dir / "world.md", "(missing world.md)")
    rules = read_text_if_exists(canon_dir / "rules.md", "(missing rules.md)")
    characters = read_text_if_exists(canon_dir / "characters.md", "(missing characters.md)")
    timeline = read_text_if_exists(canon_dir / "timeline.md", "(missing timeline.md)")
    mystery = read_text_if_exists(canon_dir / "mystery_state.md", "(missing mystery_state.md)")

    previous_summary_path = _first_existing(
        [
            summaries_dir / f"chapter_{previous}.md",
            summaries_dir / f"summary_chapter_{previous}.md",
            summaries_dir / f"chapter_{chapter_number - 1}.md",
            summaries_dir / f"summary_chapter_{chapter_number - 1}.md",
        ]
    )
    if previous_summary_path:
        previous_summary = read_text_if_exists(previous_summary_path)
    elif chapter_number <= 1:
        previous_summary = "First chapter: no previous chapter summary needed."
    else:
        previous_summary = (
            f"WARNING: previous summary not found for chapter {chapter_number - 1}. "
            "Using canon and current chapter brief only."
        )

    brief_path = _first_existing(
        [
            summaries_dir / f"chapter_{chapter}_brief.md",
            base / "chapters" / f"chapter_{chapter}_brief.md",
            base / "chapters" / f"chapter_{chapter}.md",
        ]
    )
    brief = read_text_if_exists(brief_path, "(missing current chapter brief)") if brief_path else "(missing current chapter brief)"

    output = summaries_dir / f"context_chapter_{chapter_number}.md"
    assert_write_inside_story_root(output, base)
    packet = f"""# Context Packet

## Story

```yaml
{story_config.strip()}
```

## Target Chapter

Chapter {chapter_number}

## Relevant Canon

### World

{world.strip()}

### Rules

{rules.strip()}

## Character State

{characters.strip()}

## Timeline State

{timeline.strip()}

## Mystery / Secret State

{mystery.strip()}

## Previous Chapter Summary

{previous_summary.strip()}

## Current Chapter Brief

{brief.strip()}

## Forbidden Spoilers

- Do not reveal twists or secrets before this chapter's allowed reveal point.
- Use `mystery_state.md` as hidden-state guidance, not as prose to expose.

## Open Questions

- Flag missing canon, missing summaries, or unclear character knowledge instead of inventing facts.
"""
    output.write_text(packet, encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a chapter context packet.")
    parser.add_argument("--story", required=True)
    parser.add_argument("--chapter", required=True, type=int)
    args = parser.parse_args()
    output = build_context_packet(args.story, args.chapter)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
