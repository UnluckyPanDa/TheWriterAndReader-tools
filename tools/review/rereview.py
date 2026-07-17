"""Run the one-time higher-intelligence re-review of a writer explanation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from shared.lib.config_loader import load_config
from shared.lib.model_router import attempt_model_chain, select_model_for_reviewer
from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.review_parser import REVIEW_DECISION_SCHEMA_PATH
from shared.lib.run_provenance import require_explicit_runtime_config, write_run_provenance
from shared.lib.safe_write import safe_write_file
from shared.lib.story_loader import load_story_context_file
from shared.lib.workspace_loader import resolve_story_path
from tools.review.build_review_pack import build_review_pack
from tools.review.run_review import (
    _enabled_reviewers,
    _draft_hash,
    _load_current_record,
    _load_yaml_file,
    _report_path,
    _required_codex_subagent_threads,
    _review_record_path,
    _render_report_template,
    _reviewer_profile,
    _write_review_report,
    rebuild_review_gate,
)


LAYER_CONFIG_KEYS = {
    "standard": "standard_reviewers",
    "series": "series_reviewers",
    "special": "special_reviewers",
}
INTELLIGENCE_LEVELS = ("low", "medium", "high", "very_high")


def _reviewer_settings(story_path: Path, layer: str, reviewer_id: str) -> dict[str, Any]:
    if layer not in LAYER_CONFIG_KEYS:
        raise ValueError(f"unknown reviewer layer: {layer}")
    config = _load_yaml_file(story_path / "reviewers" / "reviewer_config.yaml")
    enabled = dict(_enabled_reviewers(config, LAYER_CONFIG_KEYS[layer]))
    if reviewer_id not in enabled:
        raise ValueError(f"reviewer is missing or disabled: {layer}.{reviewer_id}")
    return enabled[reviewer_id]


def _rereview_prompt(
    story_id: str,
    chapter: int,
    layer: str,
    reviewer_id: str,
    profile: str,
    review_pack: str,
    previous_decision: str,
    explanation: str,
) -> str:
    contract = _render_report_template(story_id, chapter, layer, reviewer_id)
    return f"""Re-review one disputed fiction issue as the higher-intelligence `{reviewer_id}` reviewer.

## Reviewer Profile
{profile}

## Complete Review Pack
{review_pack}

## Previous Canonical Review Decision
{previous_decision}

## Writer Explanation
{explanation}

## Decision Rules
- Evaluate the explanation once against the draft, canon constraints, reveal lock, and exact cited passage.
- Accept the explanation only when the current prose already supports it and no reader-facing defect remains.
- If the explanation does not resolve the issue, require rewriting; do not request another explanation.
- Return one complete replacement ReviewDecisionV1 JSON object with exact evidence.
- Preserve the exact identity values in the output contract.
- Do not wrap the JSON in a Markdown fence and do not add commentary.

{contract}
"""


def _rereview_intelligence(original: str, policy: dict[str, Any]) -> str:
    """Resolve a configured level that is strictly higher than the first review."""
    if original not in INTELLIGENCE_LEVELS:
        raise ValueError(f"unknown reviewer intelligence: {original}")
    original_index = INTELLIGENCE_LEVELS.index(original)
    if original_index == len(INTELLIGENCE_LEVELS) - 1:
        raise ValueError("re-review requires intelligence higher than the original review")
    minimum = policy.get("minimum_intelligence", INTELLIGENCE_LEVELS[original_index + 1])
    if minimum not in INTELLIGENCE_LEVELS:
        raise ValueError(f"unknown re-review minimum intelligence: {minimum}")
    target_index = max(original_index + 1, INTELLIGENCE_LEVELS.index(str(minimum)))
    return INTELLIGENCE_LEVELS[target_index]


def _higher_intelligence_chain(
    model_chain: list[dict[str, Any]],
    original: str,
) -> list[dict[str, Any]]:
    """Keep only routes whose resolved intelligence exceeds the prior review."""
    original_index = INTELLIGENCE_LEVELS.index(original)
    eligible = [
        profile
        for profile in model_chain
        if profile.get("resolved_intelligence") in INTELLIGENCE_LEVELS
        and INTELLIGENCE_LEVELS.index(str(profile["resolved_intelligence"])) > original_index
    ]
    if not eligible:
        raise ValueError("re-review provider chain has no model above the original intelligence")
    return eligible


def _require_higher_result_intelligence(result: dict[str, Any], original: str) -> str:
    """Confirm the provider that actually succeeded met the re-review contract."""
    resolved = result.get("resolved_intelligence")
    if resolved not in INTELLIGENCE_LEVELS:
        raise RuntimeError("successful re-review did not report a valid resolved intelligence")
    if INTELLIGENCE_LEVELS.index(str(resolved)) <= INTELLIGENCE_LEVELS.index(original):
        raise RuntimeError("successful re-review intelligence is not higher than the original review")
    return str(resolved)


def _assert_new_rereview_thread(
    previous_record: dict[str, Any] | None,
    result: dict[str, Any],
) -> None:
    """Reject a Codex re-review that resumed the prior review thread."""
    previous_session = previous_record.get("session") if previous_record is not None else None
    current_session = result.get("session")
    previous_thread = previous_session.get("thread_id") if isinstance(previous_session, dict) else None
    current_thread = current_session.get("thread_id") if isinstance(current_session, dict) else None
    if previous_thread and current_thread == previous_thread:
        raise RuntimeError(f"re-review reused Codex thread {current_thread}")


def rereview_explanation(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    reviewer_id: str,
    explanation: str,
    config_path: str | None = None,
    layer: str = "standard",
    options: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Save one explanation, replace its report, and rebuild current gates."""
    if not explanation.strip():
        raise ValueError("writer explanation cannot be empty")
    story_path = resolve_story_path(workspace_path, story_id)
    settings = _reviewer_settings(story_path, layer, reviewer_id)
    report_path = _report_path(story_path, chapter, layer, reviewer_id)
    record_path = _review_record_path(story_path, chapter, layer, reviewer_id)
    if not report_path.exists() and not record_path.exists():
        raise FileNotFoundError(f"reviewer report is missing: {report_path}")
    explanation_path = (
        story_path
        / "reviews"
        / "chapter"
        / f"{chapter:03d}"
        / "writer_explanations"
        / f"{layer}.{reviewer_id}.md"
    )
    if explanation_path.exists():
        raise RuntimeError("writer explanation has already been used for this reviewer")

    config = load_config(config_path)
    require_explicit_runtime_config(config, "higher-intelligence re-review")
    rereview_policy = config.get("review_policy", {}).get("rereview_after_writer_explanation", {})
    if not isinstance(rereview_policy, dict):
        rereview_policy = {}
    profile = _reviewer_profile(story_path, layer, reviewer_id, settings)
    build_review_pack(workspace_path, story_id, chapter)
    review_pack = load_story_context_file(story_path, "review_pack.md")
    previous_record = _load_current_record(story_path, story_id, chapter, layer, reviewer_id)
    if record_path.exists() and previous_record is None:
        raise RuntimeError(f"current canonical review record is invalid or stale: {record_path}")
    recorded_intelligence = (
        previous_record["provider"].get("resolved_intelligence")
        if previous_record is not None
        else None
    )
    original_intelligence = (
        str(recorded_intelligence)
        if recorded_intelligence in INTELLIGENCE_LEVELS
        else str(settings.get("intelligence", "medium"))
    )
    routing = dict(settings)
    provider_group = rereview_policy.get("provider_group")
    if isinstance(provider_group, str) and provider_group:
        routing["provider_group"] = provider_group
    routing["intelligence"] = _rereview_intelligence(original_intelligence, rereview_policy)
    previous_report = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    previous_decision = (
        json.dumps(previous_record["decision"], ensure_ascii=False, indent=2)
        if previous_record is not None
        else previous_report
    )
    router_options = {**(options or {}), "output_schema_path": str(REVIEW_DECISION_SCHEMA_PATH)}
    model_chain = _higher_intelligence_chain(
        select_model_for_reviewer(config, routing),
        original_intelligence,
    )
    result = attempt_model_chain(
        _rereview_prompt(
            story_id,
            chapter,
            layer,
            reviewer_id,
            profile,
            review_pack,
            previous_decision,
            explanation,
        ),
        model_chain,
        config,
        router_options,
    )
    if not result.get("ok"):
        raise RuntimeError(f"re-review failed for all configured models: {result.get('attempts', [])}")
    resolved_intelligence = _require_higher_result_intelligence(result, original_intelligence)
    _assert_new_rereview_thread(previous_record, result)
    subagent_thread_ids = _required_codex_subagent_threads(config, result, reviewer_id)

    run_id = str(uuid4())
    draft_sha256 = _draft_hash(story_path, chapter)
    run_path = story_path / "runs" / f"chapter_{chapter:03d}" / run_id
    previous_path = run_path / f"{layer}.{reviewer_id}.previous_report.md"
    prior_artifacts = [
        (explanation_path, explanation.strip() + "\n"),
        (previous_path, previous_report.rstrip() + "\n"),
    ]
    previous_record_path: Path | None = None
    if previous_record is not None:
        previous_record_path = run_path / f"{layer}.{reviewer_id}.previous_record.json"
        prior_artifacts.append(
            (previous_record_path, json.dumps(previous_record, ensure_ascii=False, indent=2) + "\n")
        )
    for path, content in prior_artifacts:
        assert_story_write_allowed(path, story_path)
        safe_write_file(path, content, story_path)
    replaced_report, replaced_record, _ = _write_review_report(
        story_path,
        chapter,
        layer,
        reviewer_id,
        story_id,
        result,
        run_id,
        draft_sha256,
    )
    gates = rebuild_review_gate(workspace_path, story_id, chapter)
    outputs = {
        "writer_explanation": str(explanation_path.relative_to(story_path)),
        "previous_report": str(previous_path.relative_to(story_path)),
        "replacement_report": str(replaced_report.relative_to(story_path)),
        "replacement_record": str(replaced_record.relative_to(story_path)),
        **{name: str(path.relative_to(story_path)) for name, path in gates.items()},
    }
    if previous_record_path is not None:
        outputs["previous_record"] = str(previous_record_path.relative_to(story_path))
    provenance = write_run_provenance(
        story_path,
        chapter,
        "rereview",
        result,
        config,
        outputs,
        {
            "run_id": run_id,
            "reviewer": f"{layer}.{reviewer_id}",
            "original_intelligence": original_intelligence,
            "resolved_intelligence": resolved_intelligence,
            "draft_sha256": draft_sha256,
            "codex_subagent_thread_ids": subagent_thread_ids,
        },
    )
    return {
        "replacement_report": replaced_report,
        "replacement_record": replaced_record,
        "provenance": provenance,
        **gates,
    }
