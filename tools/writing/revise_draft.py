"""Apply a targeted revision mode to an existing chapter draft."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any
from uuid import uuid4

from shared.lib.config_loader import load_config
from shared.lib.model_router import attempt_model_chain, select_model_for_stage
from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.revision_evidence import (
    build_revision_receipt,
    collect_required_revision_issues,
    revision_receipt_path,
)
from shared.lib.run_provenance import require_explicit_runtime_config, write_run_provenance
from shared.lib.safe_write import safe_write_file
from shared.lib.story_loader import load_markdown_file, load_story_yaml
from shared.lib.workspace_loader import resolve_story_path
from tools.writing.build_write_pack import build_write_pack
from tools.writing.diagnose import analyze_draft
from tools.writing.generate_draft import chapter_heading, normalize_generated_draft, story_language
from tools.writing.scene_workflow import load_scene_plan


REVISION_MODES = (
    "compress",
    "deepen",
    "de-duplicate",
    "improve-dialogue",
    "strengthen-viewpoint",
    "rebalance-exposition",
    "improve-transition",
    "strengthen-hook",
    "prose-polish",
)

MODE_RULES = {
    "compress": "Remove repetition and explanation without adding events or changing scene outcomes.",
    "deepen": "Replace summary with action, interaction, physical context, and consequence while preserving events.",
    "de-duplicate": "Remove repeated meanings, phrases, gestures, images, and emotional explanations.",
    "improve-dialogue": "Strengthen intention, resistance, interruption, evasion, and subtext without adding exposition.",
    "strengthen-viewpoint": "Filter observations through the active viewpoint character's priorities and knowledge.",
    "rebalance-exposition": "Retain only information needed for immediate understanding, conflict, risk, or choice.",
    "improve-transition": "Clarify causal, spatial, and temporal movement between existing beats and scenes.",
    "strengthen-hook": "Strengthen opening pressure and the existing ending turn without inventing a new event.",
    "prose-polish": "Improve rhythm, wording, paragraph shape, and transitions without changing story content.",
}


def _write_revision_failure(
    story_path: Path,
    chapter: int,
    config: dict[str, Any],
    run_id: str,
    source_draft_sha256: str,
    required_review_issues: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    error: Exception | str,
) -> None:
    """Persist a failed revision so the loop can resume on another device."""
    write_run_provenance(
        story_path,
        chapter,
        "revision",
        {"model_profile": None, "attempts": attempts},
        config,
        {},
        {
            "run_id": run_id,
            "status": "failed",
            "failed_stage": "chapter_revision",
            "source_draft_sha256": source_draft_sha256,
            "required_review_issue_keys": [issue["key"] for issue in required_review_issues],
            "error": str(error),
        },
    )


def revision_quality_score(diagnostics: dict[str, Any]) -> float:
    """Score a candidate using the existing deterministic prose signals."""
    metrics = diagnostics.get("metrics", {})
    penalties = (
        ("repeated_phrase_count", 1.0),
        ("semantic_repetition_count", 3.0),
        ("exact_source_phrase_count", 2.0),
        ("distinctive_source_phrase_count", 1.0),
        ("paragraphs_without_state_movement", 2.0),
        ("direct_emotion_label_count", 0.5),
        ("exposition_concentration", 1.0),
    )
    return round(sum(float(metrics.get(name, 0)) * weight for name, weight in penalties), 3)


def build_revision_prompt(
    story_id: str,
    chapter: int,
    language: str,
    heading: str,
    mode: str,
    draft: str,
    write_pack: str,
    diagnostics: dict[str, Any],
    review_feedback: str,
    variation_seed: int | None = None,
    variation_factor: float | None = None,
    required_review_issues: list[dict[str, Any]] | None = None,
) -> str:
    """Build a mode-specific revision prompt with strict story boundaries."""
    if mode not in REVISION_MODES:
        raise ValueError(f"unknown revision mode: {mode}")
    return f"""Revise chapter {chapter} of story `{story_id}` in {language}.

revision_mode: {mode}
primary_rule: {MODE_RULES[mode]}

## Active Write Pack
{write_pack}

## Current Draft
{draft}

## Deterministic Diagnostics
{json.dumps(diagnostics, ensure_ascii=False, indent=2)}

## Review Feedback
{review_feedback.strip() or "No review feedback is available."}

## Required Review Issue Ledger
{json.dumps(required_review_issues or [], ensure_ascii=False, indent=2)}

## Variation Factor
variation_seed: {variation_seed if variation_seed is not None else "none"}
variation_factor: {variation_factor if variation_factor is not None else "none"}
Use this factor to make genuinely different sentence choices, paragraph openings,
image selection, and dialogue rhythm while preserving the revision contract. Do
not mention the factor in the output.

## Revision Contract
- Apply only the requested revision mode and directly relevant review targets.
- Resolve every issue in the Required Review Issue Ledger. The originating reviewer will verify each issue ID against the revised draft.
- Preserve canon, reveal timing, events, scene order, character decisions, viewpoint assignments, and ending outcome.
- Do not add characters, locations, objects, plot events, lore, or background facts.
- Do not copy wording from canon, plans, summaries, diagnostics, or reviewer reports.
- Keep concrete action, causal pressure, selective sensory detail, and meaningful dialogue.
- Return only the revised chapter, starting with this exact heading:

{heading}
"""


def build_scene_revision_prompt(
    story_id: str,
    chapter: int,
    scene_id: str,
    language: str,
    mode: str,
    scene_contract: dict[str, Any],
    scene_draft: str,
    diagnostics: dict[str, Any],
) -> str:
    """Build a targeted prompt that cannot rewrite neighboring scenes."""
    if mode not in REVISION_MODES:
        raise ValueError(f"unknown revision mode: {mode}")
    return f"""Revise only scene `{scene_id}` from story `{story_id}`, chapter {chapter}, in {language}.

revision_mode: {mode}
primary_rule: {MODE_RULES[mode]}

## Scene Contract
{json.dumps(scene_contract, ensure_ascii=False, indent=2)}

## Current Scene Draft
{scene_draft}

## Scene Diagnostics
{json.dumps(diagnostics, ensure_ascii=False, indent=2)}

## Scene Revision Contract
- Apply only the requested mode inside this scene.
- Preserve the entry condition, events, required beats, decision, state change, reveal boundaries, exit condition, and ending turn.
- Do not add facts, characters, locations, objects, or events.
- Do not write a chapter heading, scene label, commentary, or revision notes.
- Return only revised scene prose.
"""


def revise_draft(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    mode: str,
    config_path: str | None = None,
    options: dict[str, Any] | None = None,
) -> Path:
    """Run one targeted revision and replace the active draft."""
    if mode not in REVISION_MODES:
        raise ValueError(f"unknown revision mode: {mode}")
    story_path = resolve_story_path(workspace_path, story_id)
    draft_path = story_path / "drafts" / f"chapter_{chapter:03d}.md"
    draft = load_markdown_file(draft_path)
    if not draft.strip():
        raise FileNotFoundError(f"draft is missing or empty: {draft_path}")

    config = load_config(config_path)
    require_explicit_runtime_config(config, "chapter revision")
    story_yaml = load_story_yaml(story_path)
    language = story_language(story_yaml)
    heading = chapter_heading(chapter, language)
    write_pack_path = build_write_pack(str(workspace_path), story_id, chapter)
    write_pack = write_pack_path.read_text(encoding="utf-8")
    diagnostics = analyze_draft(story_path, chapter, draft)
    review_feedback = load_markdown_file(
        story_path / "reviews" / "chapter" / f"{chapter:03d}" / "combined_review.md"
    )
    source_draft_sha256 = hashlib.sha256(draft_path.read_bytes()).hexdigest()
    required_review_issues = collect_required_revision_issues(
        story_path,
        story_id,
        chapter,
        source_draft_sha256,
    )
    chain = select_model_for_stage(config, "chapter_revision", fallback_stage="chapter_generation")
    run_id = str(uuid4())
    runtime_options = dict(options or {})
    attempts_requested = max(1, int(runtime_options.pop("attempts", 1)))
    base_temperature = float(runtime_options.pop("temperature", 0.8))
    baseline_score = revision_quality_score(diagnostics)
    best_score: float | None = None
    best_draft: str | None = None
    best_result: dict[str, Any] | None = None
    candidate_scores: list[float] = []
    successful_attempts = 0
    all_attempts: list[dict[str, Any]] = []
    for attempt_index in range(attempts_requested):
        variation_seed = random.SystemRandom().randrange(1, 2**31)
        variation_factor = round(random.SystemRandom().uniform(0.15, 1.0), 3)
        prompt = build_revision_prompt(
            story_id,
            chapter,
            language,
            heading,
            mode,
            draft,
            write_pack,
            diagnostics,
            review_feedback,
            variation_seed,
            variation_factor,
            required_review_issues,
        )
        try:
            result = attempt_model_chain(
                prompt,
                chain,
                config,
                {
                    **runtime_options,
                    "temperature": base_temperature + variation_factor * 0.2,
                    "variation_seed": variation_seed,
                    "progress_label": f"chapter revision candidate {attempt_index + 1}",
                },
            )
        except Exception as exc:
            _write_revision_failure(
                story_path,
                chapter,
                config,
                run_id,
                source_draft_sha256,
                required_review_issues,
                all_attempts,
                exc,
            )
            raise
        all_attempts.extend(result.get("attempts", []))
        if not result.get("ok"):
            if attempts_requested == 1:
                error = RuntimeError(
                    f"chapter revision failed for all configured models: {result.get('attempts', [])}"
                )
                _write_revision_failure(
                    story_path,
                    chapter,
                    config,
                    run_id,
                    source_draft_sha256,
                    required_review_issues,
                    all_attempts,
                    error,
                )
                raise error
            continue
        candidate = normalize_generated_draft(str(result.get("text", "")), heading)
        if candidate.strip() == heading.strip():
            continue
        successful_attempts += 1
        candidate_diagnostics = analyze_draft(story_path, chapter, candidate)
        candidate_score = revision_quality_score(candidate_diagnostics)
        candidate_scores.append(candidate_score)
        if best_score is None or candidate_score < best_score:
            best_score = candidate_score
            best_draft = candidate
            best_result = result

    if successful_attempts == 0 or best_draft is None or best_result is None or best_score is None:
        error = RuntimeError("chapter revision produced no usable candidate")
        _write_revision_failure(
            story_path,
            chapter,
            config,
            run_id,
            source_draft_sha256,
            required_review_issues,
            all_attempts,
            error,
        )
        raise error
    revised = best_draft
    result = {**best_result, "attempts": all_attempts}
    run_path = story_path / "runs" / f"chapter_{chapter:03d}" / run_id
    source_path = run_path / "revision_source.md"
    before_path = run_path / "diagnostics_before.json"
    after_path = run_path / "diagnostics_after.json"
    receipt_history_path = run_path / "revision_issue_receipt.json"
    receipt_current_path = revision_receipt_path(story_path, chapter)
    revised_content = revised.rstrip() + "\n"
    revised_draft_sha256 = hashlib.sha256(revised_content.encode("utf-8")).hexdigest()
    receipt = build_revision_receipt(
        story_id,
        chapter,
        run_id,
        source_draft_sha256,
        revised_draft_sha256,
        required_review_issues,
    )
    after = analyze_draft(story_path, chapter, revised_content)
    for artifact_path, content in (
        (source_path, draft.rstrip() + "\n"),
        (before_path, json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n"),
        (after_path, json.dumps(after, ensure_ascii=False, indent=2) + "\n"),
        (receipt_history_path, json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"),
        (receipt_current_path, json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"),
    ):
        assert_story_write_allowed(artifact_path, story_path)
        safe_write_file(artifact_path, content, story_path)
    assert_story_write_allowed(draft_path, story_path)
    saved_path = safe_write_file(draft_path, revised_content, story_path)
    write_run_provenance(
        story_path,
        chapter,
        "revision",
        result,
        config,
        {
            "draft": str(saved_path.relative_to(story_path)),
            "source_draft": str(source_path.relative_to(story_path)),
            "diagnostics_before": str(before_path.relative_to(story_path)),
            "diagnostics_after": str(after_path.relative_to(story_path)),
            "revision_issue_receipt": str(receipt_current_path.relative_to(story_path)),
            "revision_issue_receipt_history": str(receipt_history_path.relative_to(story_path)),
            "write_pack": str(write_pack_path.relative_to(story_path)),
        },
        {
            "run_id": run_id,
            "revision_mode": mode,
            "variation_attempts": attempts_requested,
            "candidate_scores": candidate_scores,
            "baseline_score": baseline_score,
            "selected_score": best_score,
            "required_review_issue_keys": [issue["key"] for issue in required_review_issues],
        },
    )
    return saved_path


def revise_scene(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    scene_id: str,
    mode: str,
    config_path: str | None = None,
    options: dict[str, Any] | None = None,
) -> Path:
    """Revise one active scene draft without rewriting neighboring scenes."""
    if mode not in REVISION_MODES:
        raise ValueError(f"unknown revision mode: {mode}")
    story_path = resolve_story_path(workspace_path, story_id)
    write_pack_path = build_write_pack(str(workspace_path), story_id, chapter)
    write_pack = write_pack_path.read_text(encoding="utf-8")
    contract, _ = load_scene_plan(story_path, story_id, chapter, write_pack)
    contract_by_id = {str(scene["scene_id"]): scene for scene in contract["scenes"]}
    if scene_id not in contract_by_id:
        raise ValueError(f"unknown scene_id: {scene_id}")
    scene_path = story_path / "drafts" / f"chapter_{chapter:03d}_scenes" / f"{scene_id}.md"
    scene_draft = load_markdown_file(scene_path)
    if not scene_draft.strip():
        raise FileNotFoundError(f"scene draft is missing or empty: {scene_path}")
    config = load_config(config_path)
    require_explicit_runtime_config(config, "scene revision")
    language = story_language(load_story_yaml(story_path))
    diagnostics = analyze_draft(story_path, chapter, scene_draft)
    result = attempt_model_chain(
        build_scene_revision_prompt(
            story_id,
            chapter,
            scene_id,
            language,
            mode,
            contract_by_id[scene_id],
            scene_draft,
            diagnostics,
        ),
        select_model_for_stage(config, "chapter_revision", fallback_stage="chapter_generation"),
        config,
        {**(options or {}), "progress_label": f"scene revision {scene_id}"},
    )
    if not result.get("ok"):
        raise RuntimeError(f"scene revision failed for all configured models: {result.get('attempts', [])}")
    revised = str(result.get("text", "")).strip()
    lines = revised.splitlines()
    if lines and (lines[0].startswith("#") or lines[0].lower().startswith("scene ")):
        revised = "\n".join(lines[1:]).strip()
    run_id = str(uuid4())
    run_path = story_path / "runs" / f"chapter_{chapter:03d}" / run_id
    source_path = run_path / f"{scene_id}.revision_source.md"
    assert_story_write_allowed(source_path, story_path)
    safe_write_file(source_path, scene_draft.rstrip() + "\n", story_path)
    assert_story_write_allowed(scene_path, story_path)
    saved_path = safe_write_file(scene_path, revised.rstrip() + "\n", story_path)
    write_run_provenance(
        story_path,
        chapter,
        f"scene_revision_{scene_id}",
        result,
        config,
        {
            "scene_draft": str(saved_path.relative_to(story_path)),
            "source_scene": str(source_path.relative_to(story_path)),
        },
        {"run_id": run_id, "scene_id": scene_id, "revision_mode": mode},
    )
    return saved_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply a targeted chapter revision.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--story", required=True)
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--mode", required=True, choices=REVISION_MODES)
    parser.add_argument("--config")
    parser.add_argument("--attempts", type=int, default=1, help="Generate this many variations and keep the lowest diagnostic score.")
    parser.add_argument("--temperature", type=float, default=0.8, help="Base model temperature for variation attempts.")
    args = parser.parse_args(argv)
    print(revise_draft(args.workspace, args.story, args.chapter, args.mode, args.config, {"attempts": args.attempts, "temperature": args.temperature}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
