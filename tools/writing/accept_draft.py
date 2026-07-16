"""Promote a gate-approved draft and derive accepted chapter state."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from shared.lib.config_loader import load_config
from shared.lib.model_router import attempt_model_chain, select_model_for_stage
from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.run_provenance import require_explicit_runtime_config, write_run_provenance
from shared.lib.safe_write import safe_write_file
from shared.lib.workspace_loader import resolve_story_path
from shared.lib.yaml_utils import dump_yaml, load_yaml_text


def _gate_field(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*([^\n]+)$", text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip().lower() if match else ""


def _validate_gate(story_path: Path, chapter: int, draft: str) -> Path:
    gate_path = story_path / "reviews" / "chapter" / f"{chapter:03d}" / "review_gate_status.md"
    if not gate_path.exists():
        raise RuntimeError("accepted review gate is missing")
    gate = gate_path.read_text(encoding="utf-8")
    if _gate_field(gate, "run_state") != "complete":
        raise RuntimeError("review gate is incomplete")
    if _gate_field(gate, "status") not in {"accepted", "accepted_with_notes"}:
        raise RuntimeError("review gate has not accepted the draft")
    current_hash = hashlib.sha256(draft.encode("utf-8")).hexdigest()
    if _gate_field(gate, "draft_sha256") != current_hash:
        raise RuntimeError("draft changed after its accepted review")
    return gate_path


def _summary_prompt(story_id: str, chapter: int, accepted_chapter: str) -> str:
    return f"""Summarize the accepted chapter for future writing continuity.

story_id: {story_id}
chapter: {chapter}

## Accepted Chapter
{accepted_chapter}

## Summary Contract
- Derive every statement from the accepted chapter above.
- Record concrete events, decisions, discoveries, relationship changes, practical state, and unresolved pressure.
- Do not use the chapter plan, an earlier draft, reviewer speculation, or hidden canon.
- Do not invent or interpret beyond the accepted text.
- Return only concise Markdown beginning with `# Chapter {chapter:03d} Accepted Summary`.
"""


def _handover_prompt(story_id: str, chapter: int, accepted_chapter: str, summary: str) -> str:
    return f"""Create the writing handover after an accepted fiction chapter.

story_id: {story_id}
chapter: {chapter}

## Accepted Chapter
{accepted_chapter}

## Accepted Chapter Summary
{summary}

## Handover Contract
- Derive current state from the accepted chapter, supported by the accepted summary.
- Record the ending situation, character intentions, relationship state, open pressure, reader questions, and continuity details needed next.
- Keep reviewer terminology, planned-but-unwritten events, hidden canon, and revision advice out of the handover.
- Return only concise Markdown beginning with `# Story Handover`.
"""


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = load_yaml_text(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _update_state(story_path: Path, chapter: int) -> tuple[Path, Path]:
    chapter_path = story_path / "state" / "chapter_status.yaml"
    chapter_state = _load_yaml_mapping(chapter_path)
    chapter_state["current_chapter"] = chapter
    chapters = chapter_state.get("chapters")
    if not isinstance(chapters, dict):
        chapters = {}
    chapters[str(chapter)] = {"status": "accepted", "source": f"chapters/chapter_{chapter:03d}.md"}
    chapter_state["chapters"] = chapters
    assert_story_write_allowed(chapter_path, story_path)
    safe_write_file(chapter_path, dump_yaml(chapter_state, sort_keys=False), story_path)

    story_state_path = story_path / "state" / "story_status.yaml"
    story_state = _load_yaml_mapping(story_state_path)
    story_state["phase"] = "writing"
    story_state["active_chapter"] = chapter + 1
    story_state["last_accepted_chapter"] = chapter
    assert_story_write_allowed(story_state_path, story_path)
    safe_write_file(story_state_path, dump_yaml(story_state, sort_keys=False), story_path)
    return chapter_path, story_state_path


def accept_draft(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    config_path: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Promote a current accepted draft and update derived continuity files."""
    story_path = resolve_story_path(workspace_path, story_id)
    draft_path = story_path / "drafts" / f"chapter_{chapter:03d}.md"
    if not draft_path.exists() or not draft_path.read_text(encoding="utf-8").strip():
        raise FileNotFoundError(f"draft is missing or empty: {draft_path}")
    draft = draft_path.read_text(encoding="utf-8")
    gate_path = _validate_gate(story_path, chapter, draft)
    config = load_config(config_path)
    require_explicit_runtime_config(config, "accepted chapter summary and handover")
    chain = select_model_for_stage(config, "handover_update", fallback_stage="chapter_generation")
    summary_result = attempt_model_chain(_summary_prompt(story_id, chapter, draft), chain, config, options)
    if not summary_result.get("ok"):
        raise RuntimeError(f"accepted summary failed for all configured models: {summary_result.get('attempts', [])}")
    summary = str(summary_result.get("text", "")).strip()
    summary_heading = f"# Chapter {chapter:03d} Accepted Summary"
    if not summary.startswith(summary_heading):
        summary = summary_heading + "\n\n" + summary
    handover_result = attempt_model_chain(
        _handover_prompt(story_id, chapter, draft, summary),
        chain,
        config,
        options,
    )
    if not handover_result.get("ok"):
        raise RuntimeError(f"handover update failed for all configured models: {handover_result.get('attempts', [])}")
    handover = str(handover_result.get("text", "")).strip()
    if not handover.startswith("# Story Handover"):
        handover = "# Story Handover\n\n" + handover

    chapter_path = story_path / "chapters" / f"chapter_{chapter:03d}.md"
    summary_path = story_path / "summaries" / f"summary_chapter_{chapter:03d}.md"
    handover_path = story_path / "context" / "handover.md"
    for path, content in (
        (chapter_path, draft.rstrip() + "\n"),
        (summary_path, summary + "\n"),
        (handover_path, handover + "\n"),
    ):
        assert_story_write_allowed(path, story_path)
        safe_write_file(path, content, story_path)
    chapter_state_path, story_state_path = _update_state(story_path, chapter)
    run_id = str(uuid4())
    provenance_path = write_run_provenance(
        story_path,
        chapter,
        "acceptance",
        {
            "model_profile": handover_result.get("model_profile"),
            "attempts": [*summary_result.get("attempts", []), *handover_result.get("attempts", [])],
        },
        config,
        {
            "accepted_chapter": str(chapter_path.relative_to(story_path)),
            "accepted_summary": str(summary_path.relative_to(story_path)),
            "handover": str(handover_path.relative_to(story_path)),
            "chapter_state": str(chapter_state_path.relative_to(story_path)),
            "story_state": str(story_state_path.relative_to(story_path)),
            "review_gate": str(gate_path.relative_to(story_path)),
        },
        {"run_id": run_id, "source": str(draft_path.relative_to(story_path))},
    )
    return {
        "accepted_chapter": chapter_path,
        "accepted_summary": summary_path,
        "handover": handover_path,
        "chapter_state": chapter_state_path,
        "story_state": story_state_path,
        "provenance": provenance_path,
    }
