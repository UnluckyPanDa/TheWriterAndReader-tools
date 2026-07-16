"""Run the one-time higher-intelligence re-review of a writer explanation."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from shared.lib.config_loader import load_config
from shared.lib.model_router import attempt_model_chain, select_model_for_reviewer
from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.run_provenance import require_explicit_runtime_config, write_run_provenance
from shared.lib.safe_write import safe_write_file
from shared.lib.story_loader import load_story_context_file
from shared.lib.workspace_loader import resolve_story_path
from tools.review.build_review_pack import build_review_pack
from tools.review.run_review import (
    _enabled_reviewers,
    _load_yaml_file,
    _report_path,
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
    previous_report: str,
    explanation: str,
) -> str:
    contract = _render_report_template(story_id, chapter, layer, reviewer_id)
    return f"""Re-review one disputed fiction issue as the higher-intelligence `{reviewer_id}` reviewer.

## Reviewer Profile
{profile}

## Complete Review Pack
{review_pack}

## Previous Reviewer Report
{previous_report}

## Writer Explanation
{explanation}

## Decision Rules
- Evaluate the explanation once against the draft, canon constraints, reveal lock, and exact cited passage.
- Accept the explanation only when the current prose already supports it and no reader-facing defect remains.
- If the explanation does not resolve the issue, require rewriting; do not request another explanation.
- Return a complete replacement report with exact evidence.
- Preserve the metadata and headings in the output contract.

{contract}
"""


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
    if not report_path.exists():
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
    provider_group = rereview_policy.get("provider_group") if isinstance(rereview_policy, dict) else None
    routing = dict(settings)
    if isinstance(provider_group, str) and provider_group:
        routing["provider_group"] = provider_group
    profile = _reviewer_profile(story_path, layer, reviewer_id, settings)
    build_review_pack(workspace_path, story_id, chapter)
    review_pack = load_story_context_file(story_path, "review_pack.md")
    previous_report = report_path.read_text(encoding="utf-8")
    result = attempt_model_chain(
        _rereview_prompt(
            story_id,
            chapter,
            layer,
            reviewer_id,
            profile,
            review_pack,
            previous_report,
            explanation,
        ),
        select_model_for_reviewer(config, routing),
        config,
        options,
    )
    if not result.get("ok"):
        raise RuntimeError(f"re-review failed for all configured models: {result.get('attempts', [])}")

    run_id = str(uuid4())
    run_path = story_path / "runs" / f"chapter_{chapter:03d}" / run_id
    previous_path = run_path / f"{layer}.{reviewer_id}.previous_report.md"
    for path, content in (
        (explanation_path, explanation.strip() + "\n"),
        (previous_path, previous_report.rstrip() + "\n"),
    ):
        assert_story_write_allowed(path, story_path)
        safe_write_file(path, content, story_path)
    replaced_report = _write_review_report(story_path, chapter, layer, reviewer_id, result)
    gates = rebuild_review_gate(workspace_path, story_id, chapter)
    provenance = write_run_provenance(
        story_path,
        chapter,
        "rereview",
        result,
        config,
        {
            "writer_explanation": str(explanation_path.relative_to(story_path)),
            "previous_report": str(previous_path.relative_to(story_path)),
            "replacement_report": str(replaced_report.relative_to(story_path)),
            **{name: str(path.relative_to(story_path)) for name, path in gates.items()},
        },
        {"run_id": run_id, "reviewer": f"{layer}.{reviewer_id}"},
    )
    return {"replacement_report": replaced_report, "provenance": provenance, **gates}
