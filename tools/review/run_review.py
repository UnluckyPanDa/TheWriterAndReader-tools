"""Run evidence-based chapter reviewers and produce a fail-closed review gate."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from shared.lib.config_loader import load_config
from shared.lib.model_router import attempt_model_chain, select_model_for_reviewer
from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.review_parser import count_severities
from shared.lib.run_provenance import require_explicit_runtime_config, write_run_provenance
from shared.lib.safe_write import safe_write_file
from shared.lib.story_loader import load_markdown_file, load_story_context_file
from shared.lib.workspace_loader import resolve_story_path
from shared.lib.yaml_utils import load_yaml_text
from tools.review.build_review_pack import build_review_pack


REVIEWER_ROOT = Path(__file__).resolve().parent / "standard-reviewers"


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = load_yaml_text(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping: {path}")
    return data


def _enabled_reviewers(config: dict[str, Any], key: str) -> list[tuple[str, dict[str, Any]]]:
    reviewers = config.get(key, {})
    if not isinstance(reviewers, dict):
        return []
    return [
        (str(reviewer_id), reviewer_config)
        for reviewer_id, reviewer_config in sorted(reviewers.items())
        if isinstance(reviewer_config, dict) and reviewer_config.get("enabled", True)
    ]


def _reviewer_profile(story_path: Path, layer: str, reviewer_id: str, reviewer_config: dict[str, Any]) -> str:
    if layer == "standard":
        path = REVIEWER_ROOT / f"{reviewer_id}.md"
    else:
        source = reviewer_config.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"{layer} reviewer {reviewer_id} is missing its profile source")
        path = story_path / source
    profile = load_markdown_file(path)
    if not profile.strip():
        raise FileNotFoundError(f"reviewer profile is missing or empty: {path}")
    return profile


def _model_chain(config: dict[str, Any], reviewer_config: dict[str, Any]) -> list[dict[str, Any]]:
    return select_model_for_reviewer(config, reviewer_config)


def _review_prompt(
    story_id: str,
    chapter: int,
    layer: str,
    reviewer_id: str,
    reviewer_config: dict[str, Any],
    profile: str,
    review_pack: str,
) -> str:
    can_block = "yes" if reviewer_config.get("can_block_gate", True) else "no"
    return f"""You are the {layer} reviewer `{reviewer_id}` for story `{story_id}`, chapter {chapter}.

## Reviewer Profile
{profile}

## Reviewer Settings
- can_block_gate: {can_block}
- intelligence: {reviewer_config.get("intelligence", "medium")}

## Review Pack
{review_pack}

## Output Contract
Return only a Markdown review report using this exact structure:

# Review Report
reviewer_id: {reviewer_id}
reviewer_type: {layer}
story_id: {story_id}
chapter: {chapter}
status: pass | pass_with_minor_issues | needs_revision | blocked
## Summary
State the reader-facing verdict in 2-4 sentences.
## Evidence
- Location: scene, paragraph, or short quoted phrase
  Observation: what the draft does there
  Reader effect: why it works or harms the chapter
## Severity Counts
- blocker: 0
- major: 0
- minor: 0
- note: 0
## Issues
Use one `### Issue` section per issue. Each issue must include a location, `severity:`, and `rewrite_required: yes | no`.
## Rewrite Recommendation
rewrite_required: yes | no
rewrite_scope: none | sentence | paragraph | scene | chapter
## Gate Recommendation
gate_status: accept | revise | block
## Carry-Forward Tasks
## Reviewer Notes
"""


def _report_path(story_path: Path, chapter: int, layer: str, reviewer_id: str) -> Path:
    return story_path / "reviews" / "chapter" / f"{chapter:03d}" / f"{layer}.{reviewer_id}.md"


def _validate_review_report(text: str, reviewer_id: str) -> list[str]:
    required = ("# Review Report", "## Summary", "## Evidence", "## Severity Counts", "## Issues", "## Gate Recommendation")
    missing = [heading for heading in required if heading not in text]
    if not re.search(rf"^reviewer_id:\s*{re.escape(reviewer_id)}\s*$", text, re.MULTILINE):
        missing.append("matching reviewer_id")
    if not re.search(r"^status:\s*(pass|pass_with_minor_issues|needs_revision|blocked)\s*$", text, re.MULTILINE):
        missing.append("valid status")
    evidence = re.search(r"^## Evidence\s*$([\s\S]*?)(?=^## |\Z)", text, re.MULTILINE)
    if not evidence or not re.search(r"Location:\s*\S", evidence.group(1)):
        missing.append("specific evidence location")
    return missing


def _write_review_report(story_path: Path, chapter: int, layer: str, reviewer_id: str, result: dict[str, Any]) -> Path:
    text = str(result.get("text", "")).strip()
    errors = _validate_review_report(text, reviewer_id)
    if errors:
        raise RuntimeError(f"reviewer {reviewer_id} returned an invalid report: {', '.join(errors)}")
    provenance = "\n\n## Runtime Provenance\n" + f"- Model Profile: {result.get('model_profile')}\n"
    output_path = _report_path(story_path, chapter, layer, reviewer_id)
    assert_story_write_allowed(output_path, story_path)
    return safe_write_file(output_path, text + provenance, story_path)


def _report_status(text: str) -> str:
    match = re.search(r"^status:\s*([^\n]+)$", text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip().lower() if match else "invalid"


def _report_gate_recommendation(text: str) -> str:
    match = re.search(r"^gate_status:\s*([^\n]+)$", text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip().lower() if match else "invalid"


def _report_decision(text: str, can_block: bool) -> tuple[str, dict[str, int]]:
    counts = count_severities(text)
    status = _report_status(text)
    recommendation = _report_gate_recommendation(text)
    if status == "invalid" or recommendation == "invalid":
        return "blocked", counts
    if status == "blocked" or recommendation == "block" or counts["blocker"]:
        return ("blocked" if can_block else "accepted_with_notes"), counts
    if status == "needs_revision" or recommendation == "revise" or counts["major"]:
        return ("revision_recommended" if can_block else "accepted_with_notes"), counts
    if status == "pass_with_minor_issues" or counts["minor"] or counts["note"]:
        return "accepted_with_notes", counts
    if status != "pass" or recommendation != "accept":
        return "blocked", counts
    return "accepted", counts


def _combined_gate_status(decisions: list[str]) -> str:
    if "blocked" in decisions:
        return "blocked"
    if "revision_recommended" in decisions:
        return "revision_recommended"
    if "accepted_with_notes" in decisions:
        return "accepted_with_notes"
    return "accepted"


def _combine_reviews(story_path: Path, chapter: int, reports: list[Path]) -> Path:
    parts = [f"# Combined Review\n\n- Chapter: {chapter}\n- Reports: {len(reports)}"]
    for report in reports:
        parts.append(f"## {report.stem}\n\n{report.read_text(encoding='utf-8').strip()}")
    output_path = story_path / "reviews" / "chapter" / f"{chapter:03d}" / "combined_review.md"
    assert_story_write_allowed(output_path, story_path)
    return safe_write_file(output_path, "\n\n".join(parts).strip() + "\n", story_path)


def _write_gate(
    story_path: Path,
    chapter: int,
    review_rows: list[dict[str, Any]],
    combined_path: Path,
) -> tuple[Path, Path]:
    status = _combined_gate_status([str(row["decision"]) for row in review_rows])
    table_rows = ["| Reviewer | Verdict | Blockers | Majors | Minors | Key Concern |", "|----------|---------|----------|--------|--------|-------------|"]
    for row in review_rows:
        counts = row["counts"]
        table_rows.append(
            f"| {row['label']} | {row['decision']} | {counts['blocker']} | {counts['major']} | {counts['minor']} | {row['summary']} |"
        )

    failed = "fail" if status in {"blocked", "revision_recommended"} else "pass"
    gate_content = f"""# Chapter {chapter:03d} Review Gate Status

status: {status}
- Gate Status: {status}
draft: drafts/chapter_{chapter:03d}.md
review_packet: context/review_pack.md
combined_review: {combined_path.relative_to(story_path)}

## Reviewer Summary

{chr(10).join(table_rows)}

## Gate Checks

- review_contract: pass
- evidence_based_review: pass
- blocker_and_major_issues: {failed}
- prose_and_scene_quality: {failed}
- continuity_and_reveal_safety: {failed}

## Required Revisions

{"- Review the evidence-bearing issues in the combined report and revise the affected scenes before rerunning the gate." if status in {"blocked", "revision_recommended"} else "- None."}

## Decision

{status.replace('_', ' ')}. This gate is derived from evidence-bearing reviewer reports, not a missing-issue default.
"""
    gate_path = story_path / "reviews" / "chapter" / f"{chapter:03d}" / "review_gate_status.md"
    assert_story_write_allowed(gate_path, story_path)
    safe_write_file(gate_path, gate_content, story_path)

    task_content = f"""# Chapter {chapter:03d} Review Task Summary

## Current Decision

{status}.

## Review Scope

- Draft: drafts/chapter_{chapter:03d}.md
- Combined report: {combined_path.relative_to(story_path)}

## Completed Required Revisions

- None recorded by this run.

## Remaining Required Revisions

{"- Revise every blocker or major issue cited in the combined report, then rerun the affected reviewers." if status in {"blocked", "revision_recommended"} else "- None."}

## Carry-Forward Tasks

- Preserve the active chapter constraints recorded in the review pack.
"""
    task_path = story_path / "reviews" / "chapter" / f"{chapter:03d}" / "review_task_summary.md"
    assert_story_write_allowed(task_path, story_path)
    safe_write_file(task_path, task_content, story_path)
    return gate_path, task_path


def run_review(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    config_path: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Run all enabled reviewer layers and create a current-format review packet."""
    story_path = resolve_story_path(workspace_path, story_id)
    config = load_config(config_path)
    require_explicit_runtime_config(config, "chapter review")
    review_pack_path = build_review_pack(workspace_path, story_id, chapter)
    review_pack = load_story_context_file(story_path, "review_pack.md")
    reviewer_config = _load_yaml_file(story_path / "reviewers" / "reviewer_config.yaml")
    review_specs: list[tuple[str, str, dict[str, Any]]] = []
    for layer, key in (("standard", "standard_reviewers"), ("series", "series_reviewers"), ("special", "special_reviewers")):
        review_specs.extend((layer, reviewer_id, settings) for reviewer_id, settings in _enabled_reviewers(reviewer_config, key))
    if not review_specs:
        raise RuntimeError("no enabled reviewers found")

    reports: list[Path] = []
    rows: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    for layer, reviewer_id, settings in review_specs:
        profile = _reviewer_profile(story_path, layer, reviewer_id, settings)
        prompt = _review_prompt(story_id, chapter, layer, reviewer_id, settings, profile, review_pack)
        result = attempt_model_chain(prompt, _model_chain(config, settings), config, options)
        if not result.get("ok"):
            raise RuntimeError(f"reviewer {reviewer_id} failed for all configured models: {result.get('attempts', [])}")
        report_path = _write_review_report(story_path, chapter, layer, reviewer_id, result)
        text = report_path.read_text(encoding="utf-8")
        decision, counts = _report_decision(text, bool(settings.get("can_block_gate", True)))
        summary = re.sub(r"\s+", " ", text.split("## Evidence", 1)[0].split("## Summary", 1)[-1]).strip()[:120] or "No summary provided."
        reports.append(report_path)
        rows.append({"label": f"{layer}.{reviewer_id}", "decision": decision, "counts": counts, "summary": summary})
        attempts.extend(result.get("attempts", []))

    combined_path = _combine_reviews(story_path, chapter, reports)
    gate_path, task_path = _write_gate(story_path, chapter, rows, combined_path)
    write_run_provenance(
        story_path,
        chapter,
        "review",
        {"model_profile": "multiple", "attempts": attempts},
        config,
        {
            "combined_review": str(combined_path.relative_to(story_path)),
            "review_gate": str(gate_path.relative_to(story_path)),
            "review_task_summary": str(task_path.relative_to(story_path)),
        },
    )
    return {
        "review_pack": review_pack_path,
        "combined_review": combined_path,
        "review_gate": gate_path,
        "review_task_summary": task_path,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for direct module execution."""
    parser = argparse.ArgumentParser(description="Run chapter review.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--story", required=True)
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--config")
    args = parser.parse_args(argv)
    outputs = run_review(args.workspace, args.story, args.chapter, args.config)
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
