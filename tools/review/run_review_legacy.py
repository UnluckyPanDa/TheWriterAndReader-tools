from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

from scripts.build_context import (
    REPO_ROOT,
    assert_write_inside_story_root,
    build_context_packet,
    read_text_if_exists,
    resolve_story_root,
)
from scripts.ollama_client import call_ollama, select_ollama_model


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _reviewer_filter_matches(reviewer_id: str, wanted: set[str]) -> bool:
    return reviewer_id in wanted or reviewer_id.rsplit(".", 1)[-1] in wanted


def _load_story_reviewer_settings(story_id: str, repo_root: Path) -> dict[str, Any]:
    story_root = resolve_story_root(story_id, repo_root)
    for path in [story_root / "reviewers" / "story_reviewers.yaml", story_root / "reviewers.yaml"]:
        data = load_yaml(path)
        if data:
            return data
    return {}


def _override_candidates(reviewer_id: str) -> list[str]:
    candidates = [reviewer_id]
    short = reviewer_id.rsplit(".", 1)[-1]
    if short != reviewer_id:
        candidates.append(short)
    else:
        candidates.append(f"base.{reviewer_id}")
    return candidates


def _find_override(
    reviewer_id: str,
    overrides: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    for candidate in _override_candidates(reviewer_id):
        if candidate in overrides:
            return candidate, overrides[candidate]
    return None, None


def merge_reviewer_settings(
    defaults: dict[str, Any],
    story_settings: dict[str, Any],
) -> list[dict[str, Any]]:
    story_reviewers = story_settings.get("story_reviewers") or {}
    use_defaults = story_reviewers.get("use_default_reviewers", True)
    overrides = story_reviewers.get("overrides") or {}
    merged: dict[str, dict[str, Any]] = {}
    applied_overrides: set[str] = set()

    if use_defaults:
        for reviewer in defaults.get("default_reviewers", []):
            base = dict(reviewer)
            override_id, override = _find_override(str(base["id"]), overrides)
            if override is not None:
                applied_overrides.add(str(override_id))
                if str(override_id).startswith("base.") and "." not in str(base["id"]):
                    base["id"] = override_id
                base.update(override or {})
            if base.get("enabled", True):
                merged[str(base["id"])] = base

    for reviewer_id, override in overrides.items():
        if str(reviewer_id) in applied_overrides:
            continue
        base = dict(merged.get(str(reviewer_id), {"id": reviewer_id}))
        base.update(override or {})
        if base.get("enabled", True):
            merged[str(base["id"])] = base
        elif str(reviewer_id) in merged:
            del merged[str(reviewer_id)]

    for reviewer in story_reviewers.get("custom_reviewers", []) or []:
        if reviewer.get("enabled", True):
            merged[str(reviewer["id"])] = dict(reviewer)

    return list(merged.values())


def load_reviewers(
    story_id: str,
    reviewers_filter: list[str] | None = None,
    repo_root: Path = REPO_ROOT,
) -> list[dict[str, Any]]:
    defaults = load_yaml(repo_root / "config" / "reviewer_defaults.yaml")
    story_settings = _load_story_reviewer_settings(story_id, repo_root)
    reviewers = merge_reviewer_settings(defaults, story_settings)
    if reviewers_filter:
        wanted = {item.strip() for item in reviewers_filter if item.strip()}
        reviewers = [
            reviewer
            for reviewer in reviewers
            if _reviewer_filter_matches(str(reviewer.get("id", "")), wanted)
        ]
    return [reviewer for reviewer in reviewers if reviewer.get("enabled", True)]


def chapter_source(story_id: str, chapter_number: int, repo_root: Path = REPO_ROOT) -> Path | None:
    chapter = f"{chapter_number:03d}"
    base = resolve_story_root(story_id, repo_root)
    for path in [
        base / "drafts" / f"chapter_{chapter}.md",
        base / "drafts" / f"chapter-{chapter}.md",
        base / "chapters" / f"chapter_{chapter}.md",
        base / "chapters" / f"chapter-{chapter}.md",
        base / "chapters" / f"chapter_{chapter_number}.md",
    ]:
        if path.exists():
            return path
    return None


def load_reviewer_profile_text(
    reviewer: dict[str, Any],
    story_id: str,
    repo_root: Path = REPO_ROOT,
) -> str:
    profile = reviewer.get("profile")
    if not profile:
        return "(no custom reviewer profile)"

    story_root = resolve_story_root(story_id, repo_root)
    profile_path = Path(profile)
    candidates: list[Path] = []
    if profile_path.is_absolute():
        candidates.append(profile_path)
    else:
        candidates.extend(
            [
                story_root / profile_path,
                story_root / "reviewers" / "profiles" / profile_path,
                story_root / "reviewer_profiles" / profile_path,
            ]
        )
    story_root_resolved = story_root.resolve(strict=False)
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(story_root_resolved)
        except ValueError:
            continue
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
    return f"WARNING: reviewer profile not found at `{profile}`."


def build_review_prompt(
    reviewer: dict[str, Any],
    context: str,
    chapter_text: str,
    story_id: str,
    chapter_number: int,
    profile_text: str | None = None,
) -> str:
    profile_text = profile_text or "(no custom reviewer profile)"
    return f"""You are a local long-form fiction reviewer.

Reviewer id: {reviewer.get("id")}
Reviewer skill/profile: {reviewer.get("skill", reviewer.get("profile", "custom"))}
Priority: {reviewer.get("priority", reviewer.get("severity_bias", "medium"))}
Extra focus: {reviewer.get("extra_focus", [])}

Reviewer profile instructions:

{profile_text}

Hard rules:
- Do not rewrite the chapter directly.
- Do not invent new canon.
- Do not silently change canon.
- Preserve canon over model invention.
- If uncertain, flag uncertainty.
- For mystery/secret material, do not reveal future twists earlier than allowed.

Return Markdown with these sections:
# Review Report
## Summary
## Strengths
## Issues
Use bullets with Severity, Evidence, Reasoning, Suggested revision task.
## Contradiction Risks
## Canon Risks
## Spoiler Risks
## Revision Tasks
## Optional Canon Update Proposals

Context packet for story `{story_id}`, chapter {chapter_number}:

{context}

Chapter text to review:

{chapter_text}
"""


def combine_reports(reports: dict[str, str]) -> str:
    body = [
        "# Combined Review",
        "",
        "## Overall Verdict",
        "",
        "Reviewers completed. Read per-reviewer reports for evidence and exact reasoning.",
        "",
        "## Blockers",
        "",
        "- Collect blocker-severity items from reports below.",
        "",
        "## Major Issues",
        "",
        "- Collect major-severity items from reports below.",
        "",
        "## Minor Issues",
        "",
        "- Collect minor-severity items from reports below.",
        "",
        "## Revision Task List",
        "",
        "- Convert reviewer suggestions into an ordered revision pass.",
        "",
        "## Canon Update Proposals",
        "",
        "- Canon changes must be copied into `canon_updates/pending/` and accepted explicitly.",
        "",
        "## Reviewer Disagreements",
        "",
        "- Note reviewer disagreements here after reading individual reports.",
        "",
    ]
    for reviewer_id, report in reports.items():
        body.extend([f"## Report: {reviewer_id}", "", report.strip(), ""])
    return "\n".join(body)


def review_chapter(
    story_id: str,
    chapter_number: int,
    reviewers_filter: list[str] | None = None,
    repo_root: Path = REPO_ROOT,
    model: str | None = None,
    interactive_model_select: bool | None = False,
) -> dict[str, Any]:
    story_root = resolve_story_root(story_id, repo_root)
    context_path = build_context_packet(story_id, chapter_number, repo_root)
    context = context_path.read_text(encoding="utf-8")
    source = chapter_source(story_id, chapter_number, repo_root)
    chapter_text = read_text_if_exists(source, "(missing chapter draft)") if source else "(missing chapter draft)"
    reviewers = load_reviewers(story_id, reviewers_filter, repo_root)

    review_dir = story_root / "reviews" / f"chapter_{chapter_number}"
    assert_write_inside_story_root(review_dir, story_root)
    review_dir.mkdir(parents=True, exist_ok=True)

    selected_model = select_ollama_model(
        "reviewer",
        repo_root=repo_root,
        requested_model=model,
        interactive=interactive_model_select,
    )

    reports: dict[str, str] = {}
    report_paths: dict[str, Path] = {}
    for reviewer in reviewers:
        reviewer_id = reviewer["id"]
        profile_text = load_reviewer_profile_text(reviewer, story_id, repo_root)
        prompt = build_review_prompt(reviewer, context, chapter_text, story_id, chapter_number, profile_text)
        report = call_ollama(
            prompt,
            role="reviewer",
            repo_root=repo_root,
            model=selected_model,
            interactive=False,
        )
        report_path = review_dir / f"{reviewer_id}.md"
        assert_write_inside_story_root(report_path, story_root)
        report_path.write_text(report + "\n", encoding="utf-8")
        reports[reviewer_id] = report
        report_paths[reviewer_id] = report_path

    combined = combine_reports(reports)
    combined_path = review_dir / "combined_review.md"
    assert_write_inside_story_root(combined_path, story_root)
    combined_path.write_text(combined, encoding="utf-8")
    return {
        "combined": combined_path,
        "reports": report_paths,
        "context": context_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local chapter reviewers.")
    parser.add_argument("--story", required=True)
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--reviewers", default="")
    parser.add_argument("--model")
    parser.add_argument("--no-model-select", action="store_true")
    args = parser.parse_args()

    reviewers = [item.strip() for item in args.reviewers.split(",") if item.strip()] or None
    output = review_chapter(
        args.story,
        args.chapter,
        reviewers,
        model=args.model,
        interactive_model_select=not args.no_model_select,
    )
    print(output["combined"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
