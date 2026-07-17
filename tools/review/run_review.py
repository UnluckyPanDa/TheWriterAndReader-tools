"""Run evidence-based chapter reviewers and produce fail-closed quality gates."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from shared.lib.config_loader import load_config
from shared.lib.model_router import attempt_model_chain, select_model_for_reviewer
from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.review_parser import (
    REVIEW_DECISION_SCHEMA_PATH,
    parse_review_decision,
    parse_review_run_record,
    render_review_report,
    review_decision_counts,
    review_decision_gate,
    review_decision_rewrite_scope,
    review_decision_schema,
    report_decision,
    report_rewrite_scope,
    validate_review_run_record,
    validate_review_report,
)
from shared.lib.run_provenance import require_explicit_runtime_config, write_run_provenance
from shared.lib.safe_write import safe_write_file
from shared.lib.story_loader import load_markdown_file, load_story_context_file
from shared.lib.workspace_loader import resolve_story_path
from shared.lib.yaml_utils import load_yaml_text
from tools.review.build_review_pack import build_review_pack


REVIEWER_ROOT = Path(__file__).resolve().parent / "standard-reviewers"
REQUIRED_CORRECTNESS = {"continuity", "reveal_lock"}
REQUIRED_NOVELNESS = {"editor", "pacing", "tone", "character"}


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


def _render_report_template(story_id: str, chapter: int, layer: str, reviewer_id: str) -> str:
    return f"""reviewer_id: {reviewer_id}
reviewer_type: {layer}
story_id: {story_id}
chapter: {chapter}

JSON Schema:
{json.dumps(review_decision_schema(), ensure_ascii=False, indent=2)}"""


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
    contract = _render_report_template(story_id, chapter, layer, reviewer_id)
    return f"""You are the {layer} reviewer `{reviewer_id}` for story `{story_id}`, chapter {chapter}.

## Reviewer Profile
{profile}

## Reviewer Settings
- can_block_gate: {can_block}
- intelligence: {reviewer_config.get("intelligence", "medium")}

## Review Pack
{review_pack}

## Output Contract
- Return only one JSON object matching ReviewDecisionV1 below.
- Preserve the exact reviewer, story, and chapter identity values.
- Every issue must complete every schema field.
- severity_counts must exactly match the issues array.
- A pass still needs specific positive evidence with location, observation, and reader_effect.
- Do not wrap the JSON in a Markdown fence and do not add commentary.

{contract}
"""


def _report_path(story_path: Path, chapter: int, layer: str, reviewer_id: str) -> Path:
    return story_path / "reviews" / "chapter" / f"{chapter:03d}" / f"{layer}.{reviewer_id}.md"


def _review_record_path(story_path: Path, chapter: int, layer: str, reviewer_id: str) -> Path:
    return story_path / "reviews" / "chapter" / f"{chapter:03d}" / f"{layer}.{reviewer_id}.json"


def _provider_record(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(result.get("provider") or "unknown"),
        "type": str(result.get("provider_type") or "unknown"),
        "model_profile": str(result.get("model_profile") or "unknown"),
        "codex_profile": result.get("codex_profile") if isinstance(result.get("codex_profile"), str) else None,
        "model": result.get("model") if isinstance(result.get("model"), str) else None,
        "reasoning_effort": (
            result.get("reasoning_effort") if isinstance(result.get("reasoning_effort"), str) else None
        ),
        "requested_intelligence": (
            result.get("requested_intelligence")
            if isinstance(result.get("requested_intelligence"), str)
            else None
        ),
        "resolved_intelligence": (
            result.get("resolved_intelligence")
            if isinstance(result.get("resolved_intelligence"), str)
            else None
        ),
        "orchestration": str(result.get("orchestration") or "direct"),
    }


def _required_codex_subagent_threads(
    config: dict[str, Any],
    result: dict[str, Any],
    reviewer_id: str,
) -> list[str]:
    """Return verified child IDs when the successful provider requires delegation."""
    if result.get("provider_type") != "codex_cli":
        return []
    provider_id = result.get("provider")
    providers = config.get("providers", {})
    provider = providers.get(provider_id) if isinstance(providers, dict) else None
    subagents = provider.get("subagents") if isinstance(provider, dict) else None
    if not isinstance(subagents, dict) or subagents.get("required") is not True:
        return []
    session = result.get("session")
    delegation = session.get("delegation") if isinstance(session, dict) else None
    spawned = delegation.get("spawned_thread_ids") if isinstance(delegation, dict) else None
    completed = delegation.get("completed_thread_ids") if isinstance(delegation, dict) else None
    expected_count = subagents.get("count")
    if (
        result.get("orchestration") != "codex_subagent"
        or type(expected_count) is not int
        or expected_count != 1
        or not isinstance(spawned, list)
        or not isinstance(completed, list)
        or len(spawned) != expected_count
        or spawned != completed
        or any(not isinstance(thread_id, str) or not thread_id.strip() for thread_id in spawned)
    ):
        raise RuntimeError(f"reviewer {reviewer_id} did not complete its required Codex subagent")
    return [str(thread_id) for thread_id in spawned]


def _write_review_report(
    story_path: Path,
    chapter: int,
    layer: str,
    reviewer_id: str,
    story_id: str,
    result: dict[str, Any],
    run_id: str,
    draft_sha256: str,
    promote_current: bool = True,
) -> tuple[Path, Path, dict[str, Any]]:
    try:
        decision = parse_review_decision(str(result.get("text", "")), reviewer_id, layer, story_id, chapter)
    except ValueError as exc:
        raise RuntimeError(f"reviewer {reviewer_id} returned an invalid decision: {exc}") from exc
    report_path = _report_path(story_path, chapter, layer, reviewer_id)
    record_path = _review_record_path(story_path, chapter, layer, reviewer_id)
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    record = {
        "schema_version": 1,
        "run_id": run_id,
        "recorded_at": datetime.now(UTC).isoformat(),
        "draft_sha256": draft_sha256,
        "reviewer": {"id": reviewer_id, "type": layer},
        "provider": _provider_record(result),
        "session": result.get("session") if isinstance(result.get("session"), dict) else None,
        "usage": {
            str(key): int(value)
            for key, value in usage.items()
            if isinstance(value, int) and value >= 0
        },
        "outputs": {
            "decision_json": str(record_path.relative_to(story_path)),
            "report_markdown": str(report_path.relative_to(story_path)),
        },
        "decision": decision,
    }
    errors = validate_review_run_record(record)
    if errors:
        raise RuntimeError(f"reviewer {reviewer_id} produced an invalid run record: {', '.join(errors)}")
    markdown = render_review_report(decision, record)
    markdown_errors = validate_review_report(markdown, reviewer_id)
    if markdown_errors:
        raise RuntimeError(
            f"reviewer {reviewer_id} could not be rendered as a compatible report: {', '.join(markdown_errors)}"
        )
    history_path = story_path / "runs" / f"chapter_{chapter:03d}" / run_id / f"{layer}.{reviewer_id}.json"
    assert_story_write_allowed(history_path, story_path)
    safe_write_file(
        history_path,
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        story_path,
    )
    if promote_current:
        _promote_review_record(story_path, report_path, record_path, record)
    return report_path, record_path, record


def _promote_review_record(
    story_path: Path,
    report_path: Path,
    record_path: Path,
    record: dict[str, Any],
) -> None:
    """Promote one validated run record and its canonical Markdown view."""
    for path, content in (
        (record_path, json.dumps(record, ensure_ascii=False, indent=2) + "\n"),
        (report_path, render_review_report(record["decision"], record)),
    ):
        assert_story_write_allowed(path, story_path)
        safe_write_file(path, content, story_path)


def _row_from_decision(
    layer: str,
    reviewer_id: str,
    can_block: bool,
    decision: dict[str, Any],
) -> dict[str, Any]:
    summary = re.sub(r"\s+", " ", str(decision["summary"])).strip()[:120]
    return {
        "label": f"{layer}.{reviewer_id}",
        "layer": layer,
        "reviewer_id": reviewer_id,
        "can_block": can_block,
        "decision": review_decision_gate(decision, can_block),
        "counts": review_decision_counts(decision),
        "rewrite_scope": review_decision_rewrite_scope(decision),
        "summary": summary or "No summary provided.",
    }


def _load_current_record(
    story_path: Path,
    story_id: str,
    chapter: int,
    layer: str,
    reviewer_id: str,
) -> dict[str, Any] | None:
    path = _review_record_path(story_path, chapter, layer, reviewer_id)
    if not path.exists():
        return None
    try:
        record = parse_review_run_record(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    decision = record["decision"]
    if (
        record["reviewer"] != {"id": reviewer_id, "type": layer}
        or decision["story_id"] != story_id
        or decision["chapter"] != chapter
        or record["draft_sha256"] != _draft_hash(story_path, chapter)
    ):
        return None
    return record


def _legacy_review_row(
    story_path: Path,
    chapter: int,
    layer: str,
    reviewer_id: str,
    can_block: bool,
) -> tuple[Path, dict[str, Any]] | None:
    """Load a compatible Markdown-only report when no canonical JSON exists."""
    path = _report_path(story_path, chapter, layer, reviewer_id)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if validate_review_report(text, reviewer_id):
        return None
    decision, counts = report_decision(text, can_block)
    summary = re.sub(
        r"\s+",
        " ",
        text.split("## Evidence", 1)[0].split("## Summary", 1)[-1],
    ).strip()[:120]
    return path, {
        "label": f"{layer}.{reviewer_id}",
        "layer": layer,
        "reviewer_id": reviewer_id,
        "can_block": can_block,
        "decision": decision,
        "counts": counts,
        "rewrite_scope": report_rewrite_scope(text),
        "summary": summary or "No summary provided.",
    }


def _current_review_row(
    story_path: Path,
    story_id: str,
    chapter: int,
    layer: str,
    reviewer_id: str,
    can_block: bool,
) -> tuple[Path, dict[str, Any]] | None:
    """Load canonical JSON first and fail closed when an existing record is invalid."""
    record_path = _review_record_path(story_path, chapter, layer, reviewer_id)
    record = _load_current_record(story_path, story_id, chapter, layer, reviewer_id)
    if record is not None:
        report_path = _report_path(story_path, chapter, layer, reviewer_id)
        markdown = render_review_report(record["decision"], record)
        assert_story_write_allowed(report_path, story_path)
        safe_write_file(report_path, markdown, story_path)
        return report_path, _row_from_decision(layer, reviewer_id, can_block, record["decision"])
    if record_path.exists():
        return None
    return _legacy_review_row(story_path, chapter, layer, reviewer_id, can_block)


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


def _draft_hash(story_path: Path, chapter: int) -> str:
    draft_path = story_path / "drafts" / f"chapter_{chapter:03d}.md"
    if not draft_path.exists():
        return "missing"
    return hashlib.sha256(draft_path.read_bytes()).hexdigest()


def _gate_path(story_path: Path, chapter: int) -> Path:
    return story_path / "reviews" / "chapter" / f"{chapter:03d}" / "review_gate_status.md"


def _write_run_state(
    story_path: Path,
    chapter: int,
    run_id: str,
    run_state: str,
    draft_sha256: str,
    reason: str = "",
) -> Path:
    content = f"""# Chapter {chapter:03d} Review Gate Status

run_id: {run_id}
run_state: {run_state}
status: blocked
draft: drafts/chapter_{chapter:03d}.md
draft_sha256: {draft_sha256}
correctness_status: incomplete
novelness_status: incomplete
reason: {reason or 'Review run has not completed.'}
"""
    path = _gate_path(story_path, chapter)
    assert_story_write_allowed(path, story_path)
    return safe_write_file(path, content, story_path)


def _required_rows(review_rows: list[dict[str, Any]], required: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    rows = [
        row
        for row in review_rows
        if row["layer"] == "standard" and row["reviewer_id"] in required and row["can_block"]
    ]
    present = {str(row["reviewer_id"]) for row in rows}
    return rows, sorted(required - present)


def _correctness_status(review_rows: list[dict[str, Any]]) -> tuple[str, list[str]]:
    rows, missing = _required_rows(review_rows, REQUIRED_CORRECTNESS)
    if missing:
        return "incomplete", missing
    if any(row["decision"] in {"blocked", "revision_recommended"} for row in rows):
        return "fail", []
    return "pass", []


def _novelness_status(
    review_rows: list[dict[str, Any]],
    diagnostics: dict[str, Any] | None = None,
) -> tuple[str, list[str]]:
    rows, missing = _required_rows(review_rows, REQUIRED_NOVELNESS)
    if missing:
        return "incomplete", missing
    if any(row["counts"]["blocker"] or row["decision"] == "blocked" for row in rows):
        return "chapter_rewrite", []
    scopes = {str(row["rewrite_scope"]) for row in rows if row["decision"] == "revision_recommended" or row["counts"]["major"]}
    if "chapter" in scopes:
        return "chapter_rewrite", []
    if "scene" in scopes:
        return "scene_rewrite", []
    if scopes or any(row["decision"] == "revision_recommended" or row["counts"]["major"] for row in rows):
        return "targeted_revision", []
    metrics = (diagnostics or {}).get("metrics", {})
    if isinstance(metrics, dict) and int(metrics.get("exact_source_phrase_count", 0) or 0) > 0:
        return "targeted_revision", []
    if isinstance(metrics, dict) and int(metrics.get("semantic_repetition_count", 0) or 0) > 0:
        return "targeted_revision", []
    return "accept", []


def _write_novelness_gate(
    story_path: Path,
    chapter: int,
    status: str,
    missing: list[str],
    review_rows: list[dict[str, Any]],
    diagnostics: dict[str, Any] | None = None,
) -> Path:
    sources = [
        f"standard.{row['reviewer_id']}"
        for row in review_rows
        if row["layer"] == "standard" and row["reviewer_id"] in REQUIRED_NOVELNESS
    ]
    content = f"""# Chapter {chapter:03d} Novelness Gate

status: {status}
required_reviewers: {', '.join(sorted(REQUIRED_NOVELNESS))}
source_reports: {', '.join(sources) or 'none'}
missing_reviewers: {', '.join(missing) or 'none'}
diagnostics: context/chapter_{chapter:03d}_writing_diagnostics.json
exact_source_phrase_count: {(diagnostics or {}).get('metrics', {}).get('exact_source_phrase_count', 0)}
semantic_repetition_count: {(diagnostics or {}).get('metrics', {}).get('semantic_repetition_count', 0)}

## Decision

{status.replace('_', ' ')}.
"""
    path = story_path / "reviews" / "chapter" / f"{chapter:03d}" / "novelness_gate.md"
    assert_story_write_allowed(path, story_path)
    return safe_write_file(path, content, story_path)


def run_novelness_gate(workspace_path: str | Path, story_id: str, chapter: int) -> Path:
    """Rebuild the Novelness Gate from current reports and diagnostics."""
    story_path = resolve_story_path(workspace_path, story_id)
    rows: list[dict[str, Any]] = []
    for reviewer_id in sorted(REQUIRED_NOVELNESS):
        current = _current_review_row(
            story_path,
            story_id,
            chapter,
            "standard",
            reviewer_id,
            True,
        )
        if current is not None:
            rows.append(current[1])
    diagnostics_path = story_path / "context" / f"chapter_{chapter:03d}_writing_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8")) if diagnostics_path.exists() else {}
    status, missing = _novelness_status(rows, diagnostics)
    return _write_novelness_gate(story_path, chapter, status, missing, rows, diagnostics)


def rebuild_review_gate(workspace_path: str | Path, story_id: str, chapter: int) -> dict[str, Path]:
    """Rebuild combined and quality gates from current valid reviewer reports."""
    story_path = resolve_story_path(workspace_path, story_id)
    reviewer_config = _load_yaml_file(story_path / "reviewers" / "reviewer_config.yaml")
    reports: list[Path] = []
    rows: list[dict[str, Any]] = []
    for layer, key in (
        ("standard", "standard_reviewers"),
        ("series", "series_reviewers"),
        ("special", "special_reviewers"),
    ):
        for reviewer_id, settings in _enabled_reviewers(reviewer_config, key):
            can_block = bool(settings.get("can_block_gate", True))
            current = _current_review_row(
                story_path,
                story_id,
                chapter,
                layer,
                reviewer_id,
                can_block,
            )
            if current is not None:
                path, row = current
                reports.append(path)
                rows.append(row)
    if not reports:
        raise RuntimeError("no valid current reviewer reports found")
    combined_path = _combine_reviews(story_path, chapter, reports)
    diagnostics_path = story_path / "context" / f"chapter_{chapter:03d}_writing_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8")) if diagnostics_path.exists() else {}
    gate_path, task_path, novelness_path = _write_gate(
        story_path,
        chapter,
        str(uuid4()),
        _draft_hash(story_path, chapter),
        rows,
        combined_path,
        diagnostics,
    )
    return {
        "combined_review": combined_path,
        "review_gate": gate_path,
        "novelness_gate": novelness_path,
        "review_task_summary": task_path,
    }


def _write_gate(
    story_path: Path,
    chapter: int,
    run_id: str,
    draft_sha256: str,
    review_rows: list[dict[str, Any]],
    combined_path: Path,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[Path, Path, Path]:
    correctness, missing_correctness = _correctness_status(review_rows)
    novelness, missing_novelness = _novelness_status(review_rows, diagnostics)
    base_status = _combined_gate_status([str(row["decision"]) for row in review_rows])
    if correctness != "pass" or novelness in {"incomplete", "chapter_rewrite"}:
        status = "blocked"
    elif novelness in {"targeted_revision", "scene_rewrite"} or base_status == "revision_recommended":
        status = "revision_recommended"
    else:
        status = base_status

    table_rows = [
        "| Reviewer | Verdict | Blockers | Majors | Minors | Key Concern |",
        "|----------|---------|----------|--------|--------|-------------|",
    ]
    for row in review_rows:
        counts = row["counts"]
        table_rows.append(
            f"| {row['label']} | {row['decision']} | {counts['blocker']} | {counts['major']} | {counts['minor']} | {row['summary']} |"
        )

    gate_content = f"""# Chapter {chapter:03d} Review Gate Status

run_id: {run_id}
run_state: complete
status: {status}
- Gate Status: {status}
draft: drafts/chapter_{chapter:03d}.md
draft_sha256: {draft_sha256}
review_packet: context/review_pack.md
combined_review: {combined_path.relative_to(story_path)}
correctness_status: {correctness}
novelness_status: {novelness}
missing_correctness_reviewers: {', '.join(missing_correctness) or 'none'}
missing_novelness_reviewers: {', '.join(missing_novelness) or 'none'}

## Reviewer Summary

{chr(10).join(table_rows)}

## Gate Checks

- review_contract: pass
- evidence_based_review: pass
- correctness: {correctness}
- novelness: {novelness}

## Required Revisions

{"- None." if status in {"accepted", "accepted_with_notes"} else "- Resolve every failed or incomplete gate dimension, then rerun the review."}

## Decision

{status.replace('_', ' ')}. This gate is derived from evidence-bearing reviewer reports with independent correctness and novelness decisions.
"""
    gate_path = _gate_path(story_path, chapter)
    assert_story_write_allowed(gate_path, story_path)
    safe_write_file(gate_path, gate_content, story_path)

    task_content = f"""# Chapter {chapter:03d} Review Task Summary

## Current Decision

{status}.

## Review Scope

- Draft: drafts/chapter_{chapter:03d}.md
- Combined report: {combined_path.relative_to(story_path)}
- Correctness: {correctness}
- Novelness: {novelness}

## Remaining Required Revisions

{"- None." if status in {"accepted", "accepted_with_notes"} else "- Resolve the failed gate dimensions and rerun all required reviewers."}

## Carry-Forward Tasks

- Preserve the active chapter constraints recorded in the review pack.
"""
    task_path = story_path / "reviews" / "chapter" / f"{chapter:03d}" / "review_task_summary.md"
    assert_story_write_allowed(task_path, story_path)
    safe_write_file(task_path, task_content, story_path)
    novelness_path = _write_novelness_gate(
        story_path,
        chapter,
        novelness,
        missing_novelness,
        review_rows,
        diagnostics,
    )
    return gate_path, task_path, novelness_path


def run_review(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    config_path: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Run all enabled reviewer layers and create correctness and novelness gates."""
    story_path = resolve_story_path(workspace_path, story_id)
    config = load_config(config_path)
    require_explicit_runtime_config(config, "chapter review")
    run_id = str(uuid4())
    draft_sha256 = _draft_hash(story_path, chapter)
    _write_run_state(story_path, chapter, run_id, "in_progress", draft_sha256)

    try:
        review_pack_path = build_review_pack(workspace_path, story_id, chapter)
        review_pack = load_story_context_file(story_path, "review_pack.md")
        reviewer_config = _load_yaml_file(story_path / "reviewers" / "reviewer_config.yaml")
        review_specs: list[tuple[str, str, dict[str, Any]]] = []
        for layer, key in (
            ("standard", "standard_reviewers"),
            ("series", "series_reviewers"),
            ("special", "special_reviewers"),
        ):
            review_specs.extend(
                (layer, reviewer_id, settings)
                for reviewer_id, settings in _enabled_reviewers(reviewer_config, key)
            )
        if not review_specs:
            raise RuntimeError("no enabled reviewers found")

        reports: list[Path] = []
        record_paths: list[Path] = []
        rows: list[dict[str, Any]] = []
        attempts: list[dict[str, Any]] = []
        pending_records: list[tuple[Path, Path, dict[str, Any]]] = []
        codex_thread_ids: set[str] = set()
        codex_subagent_thread_ids: set[str] = set()
        seen_codex_threads: set[str] = set()
        router_options = {**(options or {}), "output_schema_path": str(REVIEW_DECISION_SCHEMA_PATH)}
        for layer, reviewer_id, settings in review_specs:
            profile = _reviewer_profile(story_path, layer, reviewer_id, settings)
            prompt = _review_prompt(story_id, chapter, layer, reviewer_id, settings, profile, review_pack)
            model_chain = _model_chain(config, settings)
            result = attempt_model_chain(prompt, model_chain, config, router_options)
            if not result.get("ok"):
                raise RuntimeError(f"reviewer {reviewer_id} failed for all configured models: {result.get('attempts', [])}")
            if result.get("provider_type") == "codex_cli":
                session = result.get("session")
                thread_id = session.get("thread_id") if isinstance(session, dict) else None
                if not isinstance(thread_id, str) or not thread_id.strip():
                    raise RuntimeError(f"reviewer {reviewer_id} did not return a fresh Codex thread")
                if thread_id in seen_codex_threads:
                    raise RuntimeError(f"reviewer {reviewer_id} reused Codex thread {thread_id}")
                codex_thread_ids.add(thread_id)
                seen_codex_threads.add(thread_id)
                for child_id in _required_codex_subagent_threads(config, result, reviewer_id):
                    if child_id in seen_codex_threads:
                        raise RuntimeError(f"reviewer {reviewer_id} reused Codex thread {child_id}")
                    codex_subagent_thread_ids.add(child_id)
                    seen_codex_threads.add(child_id)
            report_path, record_path, record = _write_review_report(
                story_path,
                chapter,
                layer,
                reviewer_id,
                story_id,
                result,
                run_id,
                draft_sha256,
                promote_current=False,
            )
            can_block = bool(settings.get("can_block_gate", True))
            reports.append(report_path)
            record_paths.append(record_path)
            pending_records.append((report_path, record_path, record))
            rows.append(_row_from_decision(layer, reviewer_id, can_block, record["decision"]))
            attempts.extend(result.get("attempts", []))

        for report_path, record_path, record in pending_records:
            _promote_review_record(story_path, report_path, record_path, record)
        combined_path = _combine_reviews(story_path, chapter, reports)
        diagnostics_path = story_path / "context" / f"chapter_{chapter:03d}_writing_diagnostics.json"
        diagnostics = (
            json.loads(diagnostics_path.read_text(encoding="utf-8"))
            if diagnostics_path.exists()
            else {}
        )
        gate_path, task_path, novelness_path = _write_gate(
            story_path,
            chapter,
            run_id,
            draft_sha256,
            rows,
            combined_path,
            diagnostics,
        )
        write_run_provenance(
            story_path,
            chapter,
            "review",
            {"model_profile": "multiple", "attempts": attempts},
            config,
            {
                "combined_review": str(combined_path.relative_to(story_path)),
                "review_gate": str(gate_path.relative_to(story_path)),
                "novelness_gate": str(novelness_path.relative_to(story_path)),
                "review_task_summary": str(task_path.relative_to(story_path)),
                "review_records": [str(path.relative_to(story_path)) for path in record_paths],
            },
            {
                "run_id": run_id,
                "draft_sha256": draft_sha256,
                "codex_thread_ids": sorted(codex_thread_ids),
                "codex_subagent_thread_ids": sorted(codex_subagent_thread_ids),
            },
        )
        return {
            "review_pack": review_pack_path,
            "combined_review": combined_path,
            "review_gate": gate_path,
            "novelness_gate": novelness_path,
            "review_task_summary": task_path,
        }
    except Exception as exc:
        _write_run_state(story_path, chapter, run_id, "failed", draft_sha256, str(exc))
        raise


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
