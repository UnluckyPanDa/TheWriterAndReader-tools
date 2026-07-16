"""Parse and validate evidence-bearing review reports."""

from __future__ import annotations

import re


SEVERITIES = ("blocker", "major", "minor", "note")
REPORT_STATUSES = ("pass", "pass_with_minor_issues", "needs_revision", "blocked")
GATE_RECOMMENDATIONS = ("accept", "revise", "block")
REVIEW_SCOPES = ("local", "scene", "chapter")
REWRITE_SCOPES = ("none", "sentence", "paragraph", "scene", "chapter")
ISSUE_TYPES = {
    "continuity",
    "reveal_timing",
    "character_consistency",
    "relationship_addressing",
    "language_clarity",
    "tone",
    "viewpoint",
    "repetition",
    "summary_instead_of_scene",
    "exposition_overload",
    "emotional_overexplanation",
    "weak_dialogue",
    "rhythm_monotony",
    "source_wording_reuse",
    "planning_language_leak",
    "pacing_local",
    "pacing_scene",
    "pacing_chapter",
    "weak_transition",
    "weak_hook",
    "other",
}


def _field(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*([^\n]+)$", text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip().lower() if match else ""


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^{re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def count_severities(text: str) -> dict[str, int]:
    """Count severity labels in review text."""
    counts = {severity: 0 for severity in SEVERITIES}
    for severity in SEVERITIES:
        counts[severity] = len(re.findall(rf"^\s*severity:\s*{severity}\s*$", text, flags=re.IGNORECASE | re.MULTILINE))
        listed = re.findall(rf"^\s*-\s*{severity}:\s*(\d+)", text, flags=re.IGNORECASE | re.MULTILINE)
        if listed:
            counts[severity] = max(counts[severity], sum(int(value) for value in listed))
    return counts


def report_status(text: str) -> str:
    return _field(text, "status") or "invalid"


def report_gate_recommendation(text: str) -> str:
    return _field(text, "gate_status") or "invalid"


def report_rewrite_scope(text: str) -> str:
    """Return the broadest declared rewrite scope."""
    values = re.findall(r"^rewrite_scope:\s*([^\n]+)$", text, re.IGNORECASE | re.MULTILINE)
    normalized = [value.strip().lower() for value in values]
    order = {name: index for index, name in enumerate(REWRITE_SCOPES)}
    valid = [value for value in normalized if value in order]
    return max(valid, key=order.__getitem__) if valid else "none"


def validate_review_report(text: str, reviewer_id: str) -> list[str]:
    """Return contract errors for a reviewer report."""
    errors: list[str] = []
    required = (
        "# Review Report",
        "## Summary",
        "## Evidence",
        "## Severity Counts",
        "## Issues",
        "## Rewrite Recommendation",
        "## Gate Recommendation",
    )
    errors.extend(heading for heading in required if heading not in text)
    if not re.search(rf"^reviewer_id:\s*{re.escape(reviewer_id)}\s*$", text, re.MULTILINE):
        errors.append("matching reviewer_id")

    status = report_status(text)
    recommendation = report_gate_recommendation(text)
    if status not in REPORT_STATUSES:
        errors.append("valid status")
    if recommendation not in GATE_RECOMMENDATIONS:
        errors.append("valid gate_status")

    evidence = _section(text, "## Evidence")
    for label in ("Location", "Observation", "Reader effect"):
        if not re.search(rf"{re.escape(label)}:\s*\S", evidence, re.IGNORECASE):
            errors.append(f"evidence {label.lower()}")

    issues = _section(text, "## Issues")
    issue_blocks = re.split(r"^###\s+Issue[^\n]*$", issues, flags=re.MULTILINE)[1:]
    for index, block in enumerate(issue_blocks, start=1):
        issue_type = _field(block, "issue_type")
        severity = _field(block, "severity")
        review_scope = _field(block, "review_scope")
        rewrite_required = _field(block, "rewrite_required")
        rewrite_scope = _field(block, "rewrite_scope")
        if issue_type not in ISSUE_TYPES:
            errors.append(f"issue {index} valid issue_type")
        if severity not in SEVERITIES:
            errors.append(f"issue {index} valid severity")
        if not _field(block, "location"):
            errors.append(f"issue {index} location")
        if not (_field(block, "observation") or _field(block, "quote")):
            errors.append(f"issue {index} observation")
        if not (_field(block, "reader_effect") or _field(block, "why_it_matters")):
            errors.append(f"issue {index} reader_effect")
        if review_scope not in REVIEW_SCOPES:
            errors.append(f"issue {index} valid review_scope")
        if rewrite_required not in {"yes", "no"}:
            errors.append(f"issue {index} valid rewrite_required")
        if rewrite_scope not in REWRITE_SCOPES:
            errors.append(f"issue {index} valid rewrite_scope")

    counts = count_severities(text)
    if status == "pass" and (recommendation != "accept" or counts["blocker"] or counts["major"]):
        errors.append("pass status consistent with findings")
    if status == "pass" and re.search(r"^rewrite_required:\s*yes\s*$", text, re.IGNORECASE | re.MULTILINE):
        errors.append("pass status cannot require rewrite")
    return errors


def report_decision(text: str, can_block: bool) -> tuple[str, dict[str, int]]:
    """Return a fail-closed reviewer decision and its severity counts."""
    counts = count_severities(text)
    status = report_status(text)
    recommendation = report_gate_recommendation(text)
    if status not in REPORT_STATUSES or recommendation not in GATE_RECOMMENDATIONS:
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


def has_required_major_rewrite(text: str) -> bool:
    """Return True when a major issue requires rewriting."""
    issue_blocks = re.split(r"^###\s+Issue[^\n]*$", text, flags=re.MULTILINE)
    return any(
        re.search(r"severity:\s*major", block, flags=re.IGNORECASE)
        and re.search(r"rewrite_required:\s*yes", block, flags=re.IGNORECASE)
        for block in issue_blocks
    )


def recommended_gate_status(text: str) -> str:
    """Derive a lightweight fail-closed status from an evidence-bearing report."""
    lowered = text.lower()
    if "status: blocked" in lowered or "severity: blocker" in lowered:
        return "blocked"
    counts = count_severities(text)
    if "status: needs_revision" in lowered or "gate_status: revise" in lowered or counts["major"]:
        return "revise"
    evidence = _section(text, "## Evidence")
    complete_evidence = all(
        re.search(rf"{label}:\s*\S", evidence, re.IGNORECASE)
        for label in ("Location", "Observation", "Reader effect")
    )
    if "status: pass" in lowered and "gate_status: accept" in lowered and complete_evidence:
        return "accepted"
    return "blocked"
