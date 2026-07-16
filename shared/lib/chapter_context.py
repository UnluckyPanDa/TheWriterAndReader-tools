"""Load the chapter-specific inputs required by writing and review workflows."""

from __future__ import annotations

from pathlib import Path

from shared.lib.story_loader import load_markdown_file


def chapter_stem(chapter: int) -> str:
    """Return the canonical zero-padded chapter filename stem."""
    return f"chapter_{chapter:03d}"


def _summary_file(story_path: Path, chapter: int, suffix: str) -> Path:
    return story_path / "summaries" / f"{chapter_stem(chapter)}_{suffix}.md"


def _first_existing(paths: list[Path]) -> tuple[str, Path | None]:
    for path in paths:
        text = load_markdown_file(path)
        if text.strip():
            return text.strip(), path
    return "", None


def load_chapter_inputs(story_path: str | Path, chapter: int) -> dict[str, str]:
    """Load active chapter direction and the nearest accepted handoff.

    Chapter-specific files take precedence over the legacy global chapter plan.
    The return values are Markdown-ready text so pack builders can state missing
    inputs explicitly instead of silently substituting stale planning material.
    """
    root = Path(story_path).expanduser().resolve(strict=False)
    brief, _ = _first_existing([_summary_file(root, chapter, "brief")])
    context, _ = _first_existing([_summary_file(root, chapter, "context")])
    instruction, _ = _first_existing([_summary_file(root, chapter, "generation_instruction")])

    previous_handoff = ""
    if chapter > 1:
        previous = chapter - 1
        previous_handoff, _ = _first_existing(
            [
                root / "reviews" / "chapter" / f"{previous:03d}" / "review_task_summary.md",
                root / "reviews" / f"chapter_{previous:03d}" / "review_task_summary.md",
                root / "summaries" / f"summary_chapter_{previous:03d}.md",
            ]
        )

    return {
        "brief": brief or "No active chapter brief was found.",
        "context": context or "No active chapter context was found.",
        "instruction": instruction or "No active chapter generation instruction was found.",
        "previous_handoff": previous_handoff or "No prior accepted review handoff was found.",
        "global_handover": load_markdown_file(root / "context" / "handover.md").strip()
        or "No global handover was found.",
        "has_active_direction": "yes" if any((brief, context, instruction)) else "no",
    }
