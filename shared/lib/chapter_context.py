"""Load the chapter-specific inputs required by writing and review workflows."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

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


def _gate_field(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*([^\n]+)$", text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip().lower() if match else ""


def _normalized_chapter_text(text: str) -> str:
    return text.rstrip()


def validate_previous_chapter_evidence(story_path: str | Path, chapter: int) -> None:
    """Fail closed when the previous gate, draft, and accepted copy diverge."""
    if chapter <= 1:
        return
    root = Path(story_path).expanduser().resolve(strict=False)
    previous = chapter - 1
    gate_text, gate_path = _first_existing(
        [
            root / "reviews" / "chapter" / f"{previous:03d}" / "review_gate_status.md",
            root / "reviews" / f"chapter_{previous:03d}" / "review_gate_status.md",
        ]
    )
    if gate_path is None:
        return

    accepted_path = root / "chapters" / f"{chapter_stem(previous)}.md"
    draft_path = root / "drafts" / f"{chapter_stem(previous)}.md"
    provenance_path = root / "runs" / f"chapter_{previous:03d}_acceptance.json"
    problems: list[str] = []

    if _gate_field(gate_text, "run_state") != "complete":
        problems.append("review gate is incomplete")
    if _gate_field(gate_text, "status") not in {"accepted", "accepted_with_notes"}:
        problems.append("review gate is not accepted")
    if not accepted_path.exists():
        problems.append("accepted chapter is missing")
    if not draft_path.exists():
        problems.append("reviewed draft is missing")

    draft_hash = ""
    if draft_path.exists():
        draft_hash = hashlib.sha256(draft_path.read_bytes()).hexdigest()
        if _gate_field(gate_text, "draft_sha256") != draft_hash:
            problems.append("review gate hash does not match the draft")
    if accepted_path.exists() and draft_path.exists():
        accepted = accepted_path.read_text(encoding="utf-8")
        draft = draft_path.read_text(encoding="utf-8")
        if _normalized_chapter_text(accepted) != _normalized_chapter_text(draft):
            problems.append("accepted prose does not match the reviewed draft")

    provenance: dict[str, object] = {}
    if not provenance_path.exists():
        problems.append("grounded acceptance provenance is missing")
    else:
        try:
            loaded = json.loads(provenance_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                provenance = loaded
            else:
                problems.append("acceptance provenance is invalid")
        except (json.JSONDecodeError, OSError):
            problems.append("acceptance provenance is invalid")
    if provenance:
        grounding = provenance.get("grounding")
        if (
            provenance.get("operation") != "acceptance"
            or provenance.get("chapter") != previous
            or provenance.get("source") != f"drafts/{chapter_stem(previous)}.md"
            or not isinstance(grounding, dict)
            or grounding.get("grounded") is not True
        ):
            problems.append("acceptance provenance is not grounded for the prior draft")
        recorded_hash = provenance.get("draft_sha256")
        if recorded_hash is not None and recorded_hash != draft_hash:
            problems.append("acceptance provenance hash does not match the draft")

    if problems:
        raise RuntimeError(
            f"cannot continue to chapter {chapter}: previous chapter {previous} acceptance evidence is inconsistent "
            f"({'; '.join(problems)}). Reconcile and re-review chapter {previous}, accept that exact draft, "
            "then regenerate its summary and handoff."
        )


def load_chapter_inputs(story_path: str | Path, chapter: int) -> dict[str, str]:
    """Load active chapter direction and the nearest accepted handoff.

    Chapter-specific files take precedence over the legacy global chapter plan.
    The return values are Markdown-ready text so pack builders can state missing
    inputs explicitly instead of silently substituting stale planning material.
    """
    root = Path(story_path).expanduser().resolve(strict=False)
    validate_previous_chapter_evidence(root, chapter)
    brief, _ = _first_existing([_summary_file(root, chapter, "brief")])
    context, _ = _first_existing([_summary_file(root, chapter, "context")])
    instruction, _ = _first_existing([_summary_file(root, chapter, "generation_instruction")])

    previous_handoff = ""
    if chapter > 1:
        previous = chapter - 1
        previous_handoff, _ = _first_existing(
            [
                root / "summaries" / f"summary_chapter_{previous:03d}.md",
                root / "reviews" / "chapter" / f"{previous:03d}" / "review_task_summary.md",
                root / "reviews" / f"chapter_{previous:03d}" / "review_task_summary.md",
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
