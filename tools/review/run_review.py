"""Run configured story reviewers and produce a review gate."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from shared.lib.config_loader import load_config
from shared.lib.model_router import attempt_model_chain, get_fallback_chain, select_model_for_reviewer
from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.review_parser import count_severities, recommended_gate_status
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


def _enabled_standard_reviewers(story_path: Path) -> list[tuple[str, dict[str, Any]]]:
    config = _load_yaml_file(story_path / "reviewers" / "reviewer_config.yaml")
    reviewers = config.get("standard_reviewers", {})
    if not isinstance(reviewers, dict):
        return []
    enabled: list[tuple[str, dict[str, Any]]] = []
    for reviewer_id, reviewer_config in sorted(reviewers.items()):
        if isinstance(reviewer_config, dict) and reviewer_config.get("enabled", True):
            enabled.append((str(reviewer_id), reviewer_config))
    return enabled


def _reviewer_profile(reviewer_id: str) -> str:
    profile = load_markdown_file(REVIEWER_ROOT / f"{reviewer_id}.md")
    if profile.strip():
        return profile
    return f"# {reviewer_id} Reviewer\nReview the draft using the standard review report template."


def _model_chain(config: dict[str, Any], reviewer_config: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        return select_model_for_reviewer(config, reviewer_config)
    except (KeyError, ValueError):
        provider_group = config.get("review_policy", {}).get("provider_group", "local_first")
        return get_fallback_chain(config, str(provider_group))


def _review_prompt(
    story_id: str,
    chapter: int,
    reviewer_id: str,
    reviewer_config: dict[str, Any],
    review_pack: str,
) -> str:
    can_block = "yes" if reviewer_config.get("can_block_gate", True) else "no"
    return f"""You are reviewer `{reviewer_id}` for story `{story_id}`, chapter {chapter}.

## Reviewer Profile
{_reviewer_profile(reviewer_id)}

## Reviewer Settings
- can_block_gate: {can_block}
- intelligence: {reviewer_config.get("intelligence", "medium")}

## Review Pack
{review_pack}

## Output Format
Return only a Markdown review report with this structure:

# Review Report
reviewer_id: {reviewer_id}
reviewer_type: standard
story_id: {story_id}
chapter: {chapter}
status: pass | pass_with_minor_issues | needs_revision | blocked
## Summary
## Severity Counts
- blocker: 0
- major: 0
- minor: 0
- note: 0
## Issues
Use one `### Issue` section per issue and include `severity:` and `rewrite_required: yes | no`.
## Rewrite Recommendation
rewrite_required: yes | no
rewrite_scope: none | sentence | paragraph | scene | chapter
## Gate Recommendation
gate_status: accept | revise | block
## Carry-Forward Tasks
## Reviewer Notes
"""


def _write_review_report(story_path: Path, chapter: int, reviewer_id: str, text: str) -> Path:
    output_path = story_path / "reviews" / f"chapter_{chapter:03d}" / f"{reviewer_id}.md"
    assert_story_write_allowed(output_path, story_path)
    return safe_write_file(output_path, text.strip() + "\n", story_path)


def combine_reviews(story_path: Path, chapter: int, reports: list[Path]) -> Path:
    """Combine individual review reports into one chapter-level report."""
    parts = [f"# Combined Review\n\n- Chapter: {chapter}\n- Reports: {len(reports)}"]
    for report in reports:
        parts.append(f"## {report.stem}\n\n{report.read_text(encoding='utf-8').strip()}")
    output_path = story_path / "reviews" / f"chapter_{chapter:03d}" / "combined_review.md"
    assert_story_write_allowed(output_path, story_path)
    return safe_write_file(output_path, "\n\n".join(parts).strip() + "\n", story_path)


def write_review_gate(story_path: Path, chapter: int, combined_path: Path) -> Path:
    """Write gate status derived from combined review text."""
    combined = combined_path.read_text(encoding="utf-8")
    status = recommended_gate_status(combined)
    counts = count_severities(combined)
    content = f"""# Review Gate Status

- Chapter: {chapter}
- Gate Status: {status}
- Blocker Issues: {counts["blocker"]}
- Major Issues: {counts["major"]}
- Minor Issues: {counts["minor"]}
- Notes: {counts["note"]}
- Combined Review: {combined_path.relative_to(story_path)}
"""
    output_path = story_path / "reviews" / f"chapter_{chapter:03d}" / "review_gate_status.md"
    assert_story_write_allowed(output_path, story_path)
    return safe_write_file(output_path, content, story_path)


def run_review(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    config_path: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Run all enabled standard reviewers for a chapter."""
    story_path = resolve_story_path(workspace_path, story_id)
    config = load_config(config_path)
    review_pack_path = build_review_pack(workspace_path, story_id, chapter)
    review_pack = load_story_context_file(story_path, "review_pack.md")
    reports: list[Path] = []

    for reviewer_id, reviewer_config in _enabled_standard_reviewers(story_path):
        prompt = _review_prompt(story_id, chapter, reviewer_id, reviewer_config, review_pack)
        result = attempt_model_chain(prompt, _model_chain(config, reviewer_config), config, options)
        if not result.get("ok"):
            attempts = result.get("attempts", [])
            raise RuntimeError(f"reviewer {reviewer_id} failed for all configured models: {attempts}")
        reports.append(_write_review_report(story_path, chapter, reviewer_id, str(result.get("text", ""))))

    if not reports:
        raise RuntimeError("no enabled standard reviewers found")

    combined_path = combine_reviews(story_path, chapter, reports)
    gate_path = write_review_gate(story_path, chapter, combined_path)
    return {"review_pack": review_pack_path, "combined_review": combined_path, "review_gate": gate_path}


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
