"""Parse and validate evidence-bearing review reports."""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"
REVIEW_DECISION_SCHEMA_PATH = SCHEMA_ROOT / "review_decision.schema.json"
REVIEW_RUN_RECORD_SCHEMA_PATH = SCHEMA_ROOT / "review_run_record.schema.json"


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
RFC3339_DATETIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


@lru_cache(maxsize=1)
def review_decision_schema() -> dict[str, Any]:
    """Load the public ReviewDecisionV1 JSON Schema."""
    return json.loads(REVIEW_DECISION_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _review_decision_validator() -> Draft202012Validator:
    schema = review_decision_schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@lru_cache(maxsize=1)
def _review_run_record_validator() -> Draft202012Validator:
    schema = json.loads(REVIEW_RUN_RECORD_SCHEMA_PATH.read_text(encoding="utf-8"))
    expanded = copy.deepcopy(schema)
    expanded["properties"]["decision"] = review_decision_schema()
    Draft202012Validator.check_schema(expanded)
    return Draft202012Validator(expanded, format_checker=FormatChecker())


def _schema_messages(validator: Draft202012Validator, data: Any) -> list[str]:
    messages: list[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path))[:8]:
        location = ".".join(str(part) for part in error.absolute_path) or "root"
        messages.append(f"{location}: {error.message}")
    return messages


def validate_review_decision(
    data: Any,
    reviewer_id: str | None = None,
    reviewer_type: str | None = None,
    story_id: str | None = None,
    chapter: int | None = None,
) -> list[str]:
    """Return schema and semantic errors for a ReviewDecisionV1 object."""
    errors = _schema_messages(_review_decision_validator(), data)
    if errors or not isinstance(data, dict):
        return errors

    expected = {
        "reviewer_id": reviewer_id,
        "reviewer_type": reviewer_type,
        "story_id": story_id,
        "chapter": chapter,
    }
    for field, value in expected.items():
        if value is not None and data.get(field) != value:
            errors.append(f"{field} must be {value}")

    actual_counts = {severity: 0 for severity in SEVERITIES}
    issue_ids: list[str] = []
    scope_order = {name: index for index, name in enumerate(REWRITE_SCOPES)}
    required_scopes: list[str] = []
    for issue in data["issues"]:
        actual_counts[issue["severity"]] += 1
        issue_ids.append(issue["issue_id"])
        if issue["rewrite_required"]:
            required_scopes.append(issue["rewrite_scope"])
            if issue["rewrite_scope"] == "none":
                errors.append(f"issue {issue['issue_id']} requires a non-none rewrite_scope")
        elif issue["rewrite_scope"] != "none":
            errors.append(f"issue {issue['issue_id']} without rewrite must use rewrite_scope none")
        for field in ("location", "observation", "reader_effect", "suggested_fix"):
            if not issue[field].strip():
                errors.append(f"issue {issue['issue_id']} {field} cannot be blank")
    if len(issue_ids) != len(set(issue_ids)):
        errors.append("issue_id values must be unique")
    if data["severity_counts"] != actual_counts:
        errors.append("severity_counts must exactly match issues")

    recommendation = data["rewrite_recommendation"]
    has_required_rewrite = bool(required_scopes)
    if recommendation["required"] != has_required_rewrite:
        errors.append("rewrite_recommendation.required must match issue rewrite requirements")
    if recommendation["required"]:
        if recommendation["scope"] == "none":
            errors.append("required rewrite_recommendation must use a non-none scope")
        elif required_scopes and scope_order[recommendation["scope"]] < max(
            scope_order[scope] for scope in required_scopes
        ):
            errors.append("rewrite_recommendation.scope cannot be narrower than an issue rewrite_scope")
    elif recommendation["scope"] != "none":
        errors.append("non-required rewrite_recommendation must use scope none")

    expected_gate = {
        "pass": "accept",
        "pass_with_minor_issues": "accept",
        "needs_revision": "revise",
        "blocked": "block",
    }[data["status"]]
    if data["gate_recommendation"] != expected_gate:
        errors.append(f"status {data['status']} requires gate_recommendation {expected_gate}")
    if data["status"] in {"pass", "pass_with_minor_issues"}:
        if actual_counts["blocker"] or actual_counts["major"]:
            errors.append(f"status {data['status']} cannot include blocker or major issues")
        if recommendation["required"]:
            errors.append(f"status {data['status']} cannot require rewriting")
    return errors


def parse_review_decision(
    text: str,
    reviewer_id: str,
    reviewer_type: str,
    story_id: str,
    chapter: int,
) -> dict[str, Any]:
    """Parse and validate strict model-produced ReviewDecisionV1 JSON."""
    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"review decision is not valid JSON: {exc.msg}") from exc
    errors = validate_review_decision(data, reviewer_id, reviewer_type, story_id, chapter)
    if errors:
        raise ValueError("invalid review decision: " + "; ".join(errors))
    return data


def validate_review_run_record(data: Any) -> list[str]:
    """Return schema and cross-envelope errors for ReviewRunRecordV1."""
    errors = _schema_messages(_review_run_record_validator(), data)
    if errors or not isinstance(data, dict):
        return errors
    recorded_at = data["recorded_at"]
    if not RFC3339_DATETIME.fullmatch(recorded_at):
        errors.append("recorded_at must be an RFC 3339 date-time")
    else:
        try:
            parsed_timestamp = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("recorded_at must be an RFC 3339 date-time")
        else:
            if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
                errors.append("recorded_at must be an RFC 3339 date-time")
    reviewer = data["reviewer"]
    decision = data["decision"]
    errors.extend(
        validate_review_decision(
            decision,
            str(reviewer["id"]),
            str(reviewer["type"]),
            str(decision["story_id"]),
            int(decision["chapter"]),
        )
    )
    provider = data["provider"]
    session = data["session"]
    if provider["type"] == "codex_cli":
        if not isinstance(session, dict):
            errors.append("codex_cli review run requires session metadata")
        else:
            if session["start_mode"] != "fresh":
                errors.append("codex_cli review must start a fresh session")
            if not isinstance(session["thread_id"], str) or not session["thread_id"].strip():
                errors.append("codex_cli review requires a thread_id")
            if session["resumed_from"] is not None:
                errors.append("fresh codex_cli review cannot resume another session")
        for field in ("codex_profile", "model", "reasoning_effort", "resolved_intelligence"):
            if not isinstance(provider[field], str) or not provider[field].strip():
                errors.append(f"codex_cli provider requires {field}")
    elif session is not None:
        errors.append("non-threaded review providers must use session null")
    return errors


def parse_review_run_record(text: str) -> dict[str, Any]:
    """Parse a trusted ReviewRunRecordV1 artifact."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"review run record is not valid JSON: {exc.msg}") from exc
    errors = validate_review_run_record(data)
    if errors:
        raise ValueError("invalid review run record: " + "; ".join(errors))
    return data


def review_decision_counts(decision: dict[str, Any]) -> dict[str, int]:
    """Return trusted severity counts from a validated decision."""
    return {severity: int(decision["severity_counts"][severity]) for severity in SEVERITIES}


def review_decision_rewrite_scope(decision: dict[str, Any]) -> str:
    """Return the aggregate rewrite scope from a validated decision."""
    return str(decision["rewrite_recommendation"]["scope"])


def review_decision_gate(decision: dict[str, Any], can_block: bool) -> str:
    """Map a validated decision to the existing combined-gate vocabulary."""
    status = str(decision["status"])
    counts = review_decision_counts(decision)
    if status == "blocked" or counts["blocker"]:
        return "blocked" if can_block else "accepted_with_notes"
    if status == "needs_revision" or counts["major"]:
        return "revision_recommended" if can_block else "accepted_with_notes"
    if status == "pass_with_minor_issues" or counts["minor"] or counts["note"]:
        return "accepted_with_notes"
    return "accepted"


def _markdown_list(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values) if values else "None."


def render_review_report(decision: dict[str, Any], runtime: dict[str, Any] | None = None) -> str:
    """Render a stable Markdown view from canonical review JSON."""
    lines = [
        "# Review Report",
        f"reviewer_id: {decision['reviewer_id']}",
        f"reviewer_type: {decision['reviewer_type']}",
        f"story_id: {decision['story_id']}",
        f"chapter: {decision['chapter']}",
        f"status: {decision['status']}",
        "## Summary",
        str(decision["summary"]),
        "## Evidence",
    ]
    for evidence in decision["evidence"]:
        lines.extend(
            [
                f"- Location: {evidence['location']}",
                f"  Observation: {evidence['observation']}",
                f"  Reader effect: {evidence['reader_effect']}",
            ]
        )
    counts = review_decision_counts(decision)
    lines.extend(
        [
            "## Severity Counts",
            *[f"- {severity}: {counts[severity]}" for severity in SEVERITIES],
            "## Issues",
        ]
    )
    for issue in decision["issues"]:
        lines.extend(
            [
                f"### Issue {issue['issue_id']}",
                f"issue_type: {issue['issue_type']}",
                f"severity: {issue['severity']}",
                f"location: {issue['location']}",
                f"observation: {issue['observation']}",
                f"reader_effect: {issue['reader_effect']}",
                f"review_scope: {issue['review_scope']}",
                f"rewrite_required: {'yes' if issue['rewrite_required'] else 'no'}",
                f"rewrite_scope: {issue['rewrite_scope']}",
                f"suggested_fix: {issue['suggested_fix']}",
            ]
        )
    recommendation = decision["rewrite_recommendation"]
    lines.extend(
        [
            "## Rewrite Recommendation",
            f"rewrite_required: {'yes' if recommendation['required'] else 'no'}",
            f"rewrite_scope: {recommendation['scope']}",
            "## Gate Recommendation",
            f"gate_status: {decision['gate_recommendation']}",
            "## Carry-Forward Tasks",
            _markdown_list(decision["carry_forward_tasks"]),
            "## Reviewer Notes",
            _markdown_list(decision["reviewer_notes"]),
        ]
    )
    if runtime:
        provider = runtime.get("provider", {})
        session = runtime.get("session") or {}
        lines.extend(
            [
                "## Runtime Provenance",
                f"- Model Profile: {provider.get('model_profile')}",
                f"- Provider: {provider.get('id')}",
                f"- Provider Type: {provider.get('type')}",
                f"- Codex Profile: {provider.get('codex_profile') or 'none'}",
                f"- Model: {provider.get('model') or 'unspecified'}",
                f"- Reasoning Effort: {provider.get('reasoning_effort') or 'unspecified'}",
                f"- Session Start: {session.get('start_mode', 'stateless')}",
                f"- Session Retention: {session.get('retention', 'none')}",
                f"- Thread ID: {session.get('thread_id') or 'none'}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


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
