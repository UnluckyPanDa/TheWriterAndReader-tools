"""Parse and validate evidence-bearing review reports."""

from __future__ import annotations

import copy
import hashlib
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
    flexible: bool = False,
) -> dict[str, Any]:
    """Parse a strict V1 decision, or a flexible boundary result when requested."""
    if flexible:
        return normalize_review_decision(text, reviewer_id, reviewer_type, story_id, chapter)["canonical"]
    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"review decision is not valid JSON: {exc.msg}") from exc
    errors = validate_review_decision(data, reviewer_id, reviewer_type, story_id, chapter)
    if errors:
        raise ValueError("invalid review decision: " + "; ".join(errors))
    return data


def _json_candidates(text: str) -> list[tuple[str, str]]:
    """Return direct, fenced, and embedded JSON candidates in source order."""
    stripped = text.strip()
    candidates: list[tuple[str, str]] = [("json", stripped)] if stripped else []
    for match in re.finditer(r"```(?:json|javascript|js)?\s*([\s\S]*?)```", stripped, re.IGNORECASE):
        candidates.append(("fenced_json", match.group(1).strip()))
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", stripped):
        try:
            _, end = decoder.raw_decode(stripped[match.start() :])
        except json.JSONDecodeError:
            continue
        candidates.append(("embedded_json", stripped[match.start() : match.start() + end]))
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for source, candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append((source, candidate))
    return unique


def _first_value(data: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in data and data[name] not in (None, ""):
            return data[name]
    return None


def _text_value(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "; ".join(_text_value(item) for item in value if _text_value(item))
    if isinstance(value, dict):
        return "; ".join(
            f"{key}: {_text_value(item)}" for key, item in value.items() if _text_value(item)
        )
    return default


def _bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"yes", "true", "1", "required", "rewrite", "needs_revision", "revise"}:
            return True
        if lowered in {"no", "false", "0", "none", "accept", "accepted", "pass"}:
            return False
    return default


def _normalized_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _text_value(value).casefold()).strip("_")


def _status_value(value: Any) -> str | None:
    token = _normalized_token(value)
    if token in {"pass", "passed", "accept", "accepted", "approved", "ok", "clear", "go"}:
        return "pass"
    if token in {"pass_with_minor_issues", "accepted_with_notes", "pass_with_notes", "minor_issues"}:
        return "pass_with_minor_issues"
    if token in {"needs_revision", "revision_required", "revise_required", "revision_recommended", "revise", "revision", "changes_required", "fail"}:
        return "needs_revision"
    if token in {"blocked", "block", "reject", "rejected", "unsafe", "stop"}:
        return "blocked"
    return None


def _severity_value(value: Any, default: str | None = None) -> str | None:
    token = _normalized_token(value)
    aliases = {
        "critical": "blocker",
        "urgent": "blocker",
        "high": "major",
        "warning": "minor",
        "medium": "minor",
        "info": "note",
        "informational": "note",
    }
    token = aliases.get(token, token)
    return token if token in SEVERITIES else default


def _scope_value(value: Any, default: str = "chapter") -> str:
    token = _normalized_token(value)
    aliases = {"line": "sentence", "paragraphs": "paragraph", "scenes": "scene", "chapters": "chapter"}
    token = aliases.get(token, token)
    return token if token in REWRITE_SCOPES else default


def _review_scope_value(value: Any) -> str:
    token = _normalized_token(value)
    aliases = {"passage": "local", "line": "local", "scene_level": "scene", "chapter_level": "chapter"}
    token = aliases.get(token, token)
    return token if token in REVIEW_SCOPES else "chapter"


def _stable_issue_id(issue: dict[str, Any], index: int) -> str:
    existing = _text_value(issue.get("issue_id"))
    if re.fullmatch(r"R\d{3,}", existing):
        return existing
    material = "|".join(
        _text_value(issue.get(field))
        for field in ("issue_type", "severity", "location", "observation", "reader_effect", "suggested_fix")
    )
    digest = int(hashlib.sha256(material.encode("utf-8")).hexdigest()[:12], 16)
    return f"R{digest % 1_000_000_000:09d}" if material else f"R{index:03d}"


def _as_evidence(value: Any) -> list[dict[str, str]]:
    if isinstance(value, dict):
        value = [value]
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    evidence: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                evidence.append(
                    {
                        "location": "review output",
                        "observation": text,
                        "reader_effect": "The observation is relevant to the chapter review.",
                    }
                )
            continue
        if not isinstance(item, dict):
            continue
        location = _text_value(_first_value(item, "location", "where", "at", "section"))
        observation = _text_value(_first_value(item, "observation", "finding", "description", "quote"))
        effect = _text_value(_first_value(item, "reader_effect", "impact", "why_it_matters", "effect"))
        if location and observation and effect:
            evidence.append({"location": location, "observation": observation, "reader_effect": effect})
    return evidence


def _as_issue_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = [value]
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    issues: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                issues.append({"observation": text})
            continue
        if isinstance(item, dict):
            issues.append(dict(item))
    return issues


def _canonicalize_mapping(
    data: dict[str, Any],
    reviewer_id: str,
    reviewer_type: str,
    story_id: str,
    chapter: int,
) -> tuple[dict[str, Any], list[str], list[str]]:
    warnings: list[str] = []
    inferred: list[str] = ["reviewer_id", "reviewer_type", "story_id", "chapter", "severity_counts", "gate_recommendation"]
    nested = _first_value(data, "decision", "review_decision", "review", "result")
    if isinstance(nested, dict) and not any(key in data for key in ("status", "verdict", "outcome", "findings", "issues")):
        data = nested
        inferred.append("decision_container")

    raw_status = _first_value(data, "status", "verdict", "outcome", "decision", "result")
    status = _status_value(raw_status)
    raw_issues = _first_value(data, "issues", "findings", "concerns", "problems", "violations", "comments")
    issue_items = _as_issue_list(raw_issues)
    raw_evidence = _first_value(data, "evidence", "observations", "supporting_evidence")
    evidence = _as_evidence(raw_evidence)
    canonical_issues: list[dict[str, Any]] = []
    for index, raw_issue in enumerate(issue_items, start=1):
        severity = _severity_value(
            _first_value(raw_issue, "severity", "level", "priority", "impact"),
        )
        observation = _text_value(_first_value(raw_issue, "observation", "finding", "description", "problem", "quote"))
        status_hint = status or "needs_revision"
        if severity is None and observation:
            lowered = observation.casefold()
            severity = _severity_value(
                "blocker" if any(word in lowered for word in ("unsafe", "fatal", "critical", "impossible")) else
                "major" if status_hint == "needs_revision" else "minor"
            )
            warnings.append(f"inferred severity for issue {index}")
            inferred.append("issue_severity")
        if severity is None:
            raise ValueError(f"review issue {index} lacks a semantically clear severity")
        location = _text_value(_first_value(raw_issue, "location", "where", "at", "section"))
        observation = observation or _text_value(_first_value(raw_issue, "summary", "text"))
        reader_effect = _text_value(_first_value(raw_issue, "reader_effect", "impact", "why_it_matters", "effect"))
        suggested_fix = _text_value(_first_value(raw_issue, "suggested_fix", "fix", "recommendation", "action"))
        if not location or not observation or not reader_effect:
            raise ValueError(f"review issue {index} lacks required evidence")
        rewrite_required = _bool_value(
            _first_value(raw_issue, "rewrite_required", "needs_revision", "rewrite", "required"),
            severity in {"blocker", "major"} or status_hint == "needs_revision",
        )
        rewrite_scope = _scope_value(
            _first_value(raw_issue, "rewrite_scope", "scope", "rewrite_level"),
            "chapter" if rewrite_required else "none",
        )
        if not rewrite_required:
            rewrite_scope = "none"
        canonical_issue = {
            "issue_id": _stable_issue_id(raw_issue, index),
            "issue_type": _normalized_token(_first_value(raw_issue, "issue_type", "type", "category", "kind")) or "other",
            "severity": severity,
            "location": location,
            "observation": observation,
            "reader_effect": reader_effect,
            "review_scope": _review_scope_value(_first_value(raw_issue, "review_scope", "level_scope")),
            "rewrite_required": rewrite_required,
            "rewrite_scope": rewrite_scope,
            "suggested_fix": suggested_fix or "Address the cited issue in the indicated scope.",
        }
        if canonical_issue["issue_type"] not in ISSUE_TYPES:
            canonical_issue["issue_type"] = "other"
            warnings.append(f"mapped unsupported issue type to other for issue {index}")
        canonical_issues.append(canonical_issue)
        if not evidence:
            evidence.append(
                {
                    "location": location,
                    "observation": observation,
                    "reader_effect": reader_effect,
                }
            )

    summary = _text_value(_first_value(data, "summary", "overall", "assessment", "conclusion", "notes"))
    if not summary:
        summary = "Review completed with evidence-bearing findings." if canonical_issues else "Review completed."
        inferred.append("summary")
    if status is None:
        if any(issue["severity"] == "blocker" for issue in canonical_issues):
            status = "blocked"
        elif any(issue["rewrite_required"] for issue in canonical_issues):
            status = "needs_revision"
        elif any(issue["severity"] in {"minor", "note"} for issue in canonical_issues):
            status = "pass_with_minor_issues"
        else:
            status = "pass"
        inferred.append("status")
    explicit_gate = _status_value(_first_value(data, "gate_recommendation", "gate", "gate_status"))
    if explicit_gate is not None:
        explicit_gate = {"pass": "accept", "pass_with_minor_issues": "accept", "needs_revision": "revise", "blocked": "block"}[explicit_gate]
    gate = {"pass": "accept", "pass_with_minor_issues": "accept", "needs_revision": "revise", "blocked": "block"}[status]
    if explicit_gate and explicit_gate != gate:
        raise ValueError("review status and gate recommendation are contradictory")
    if status in {"pass", "pass_with_minor_issues"} and any(issue["severity"] in {"blocker", "major"} for issue in canonical_issues):
        raise ValueError("review pass status contradicts blocker or major evidence")
    if not evidence:
        raise ValueError("review output lacks required evidence")

    counts = {severity: sum(issue["severity"] == severity for issue in canonical_issues) for severity in SEVERITIES}
    required_scopes = [issue["rewrite_scope"] for issue in canonical_issues if issue["rewrite_required"]]
    scope_order = {name: index for index, name in enumerate(REWRITE_SCOPES)}
    rewrite_scope = max(required_scopes, key=scope_order.__getitem__) if required_scopes else "none"
    raw_tasks = _first_value(data, "carry_forward_tasks", "follow_up", "next_steps") or []
    raw_notes = _first_value(data, "reviewer_notes", "review_notes", "notes") or []
    if isinstance(raw_tasks, str):
        raw_tasks = [raw_tasks]
    if isinstance(raw_notes, str):
        raw_notes = [raw_notes]
    canonical = {
        "schema_version": 1,
        "reviewer_id": reviewer_id,
        "reviewer_type": reviewer_type,
        "story_id": story_id,
        "chapter": chapter,
        "status": status,
        "summary": summary,
        "evidence": evidence,
        "severity_counts": counts,
        "issues": canonical_issues,
        "rewrite_recommendation": {"required": bool(required_scopes), "scope": rewrite_scope},
        "gate_recommendation": gate,
        "carry_forward_tasks": [
            _text_value(item)
            for item in raw_tasks
            if _text_value(item)
        ],
        "reviewer_notes": [
            _text_value(item)
            for item in raw_notes
            if _text_value(item)
        ],
    }
    return canonical, inferred, warnings


def _markdown_field(text: str, *aliases: str) -> str:
    for alias in aliases:
        match = re.search(
            rf"^\s*(?:[-*+]\s+)?(?:\*\*|__)?\s*{re.escape(alias)}(?:\*\*|__)?\s*:\s*(?:\*\*|__)?\s*(.+?)\s*$",
            text,
            re.IGNORECASE | re.MULTILINE,
        )
        if match:
            return re.sub(r"(?:\*\*|__)\s*$", "", match.group(1).strip()).strip()
    return ""


def _markdown_table_issues(section: str) -> list[dict[str, str]]:
    rows = [line.strip() for line in section.splitlines() if line.strip().startswith("|")]
    if len(rows) < 2:
        return []
    headers = [_normalized_token(cell) for cell in rows[0].strip("|").split("|")]
    aliases = {
        "severity": "severity",
        "location": "location",
        "where": "location",
        "observation": "observation",
        "finding": "observation",
        "description": "observation",
        "impact": "reader_effect",
        "impact_on_reader": "reader_effect",
        "reader_effect": "reader_effect",
        "why_it_matters": "reader_effect",
        "issue_id": "issue_id",
        "id": "issue_id",
        "suggested_fix": "suggested_fix",
        "fix": "suggested_fix",
        "recommendation": "suggested_fix",
    }
    fields = [aliases.get(header) for header in headers]
    issues: list[dict[str, str]] = []
    for row in rows[1:]:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        if cells and all(not cell or set(cell) <= {":", "-", " "} for cell in cells):
            continue
        if len(cells) != len(fields):
            continue
        issue = {
            field: cell
            for field, cell in zip(fields, cells)
            if field and cell
        }
        if issue:
            issues.append(issue)
    return issues


def _markdown_mapping(text: str) -> dict[str, Any]:
    """Extract common current and legacy Markdown review layouts."""
    cleaned = re.sub(r"^\s*```(?:markdown|md)?\s*|\s*```\s*$", "", text.strip(), flags=re.IGNORECASE)
    mapping: dict[str, Any] = {}
    for name in (
        "reviewer_id", "reviewer_type", "story_id", "chapter", "status", "gate_status",
        "gate_recommendation", "gate_decision", "reviewer", "reviewer_type", "decision", "verdict", "severity",
    ):
        value = _markdown_field(cleaned, name)
        if value:
            mapping[name] = value
    if mapping.get("gate_decision") and not mapping.get("gate_status"):
        mapping["gate_status"] = mapping["gate_decision"]
    summary = (
        _section(cleaned, "## Summary")
        or _section(cleaned, "# Summary")
        or _section(cleaned, "## Review Summary")
        or _section(cleaned, "### Review Summary")
    )
    if summary:
        mapping["summary"] = summary
    evidence = _section(cleaned, "## Evidence") or _section(cleaned, "# Evidence")
    evidence_items: list[dict[str, str]] = []
    blocks = re.split(r"(?=^\s*[-*]\s*Location\s*:)", evidence, flags=re.IGNORECASE | re.MULTILINE)
    for block in blocks:
        location = re.search(r"Location\s*:\s*(.+)", block, re.IGNORECASE)
        observation = re.search(r"Observation\s*:\s*(.+)", block, re.IGNORECASE)
        effect = re.search(r"Reader effect\s*:\s*(.+)", block, re.IGNORECASE)
        if location and observation and effect:
            evidence_items.append({"location": location.group(1).strip(), "observation": observation.group(1).strip(), "reader_effect": effect.group(1).strip()})
    if evidence_items:
        mapping["evidence"] = evidence_items
    issues_section = (
        _section(cleaned, "## Issues")
        or _section(cleaned, "# Issues")
        or _section(cleaned, "## Findings")
        or _section(cleaned, "## Review Findings")
        or _section(cleaned, "## Findings & Issues")
        or _section(cleaned, "### Findings & Issues")
        or _section(cleaned, "### Findings")
        or _section(cleaned, "### Review Findings")
        or _section(cleaned, "## Issues Found")
        or _section(cleaned, "### Issues Found")
    )
    issues: list[dict[str, Any]] = list(_markdown_table_issues(issues_section))
    issue_blocks = re.split(
        r"^\s*(?:#{2,4}\s*)?(?:\*\*|__)?\s*(?:Issue|Finding|Concern)\b[^\n]*?(?:\*\*|__)?\s*$",
        issues_section,
        flags=re.IGNORECASE | re.MULTILINE,
    )[1:]
    for block in issue_blocks:
        item: dict[str, Any] = {}
        for name, aliases in {
            "issue_id": ("issue_id", "id"), "issue_type": ("issue_type", "type", "category"),
            "severity": ("severity", "level", "priority"), "location": ("location", "where"),
            "observation": ("observation", "finding", "description", "quote"),
            "reader_effect": ("reader_effect", "why_it_matters", "impact"),
            "rewrite_required": ("rewrite_required", "needs_revision"),
            "rewrite_scope": ("rewrite_scope", "scope"), "suggested_fix": ("suggested_fix", "fix", "recommendation"),
        }.items():
            value = _markdown_field(block, *aliases)
            if value:
                item[name] = value
        if "severity" not in item and mapping.get("severity"):
            item["severity"] = mapping["severity"]
        if item:
            issues.append(item)
    if issues:
        mapping["issues"] = issues
    return mapping


def normalize_review_decision(
    text: str,
    reviewer_id: str,
    reviewer_type: str,
    story_id: str,
    chapter: int,
    semantic_normalizer: Any | None = None,
) -> dict[str, Any]:
    """Normalize flexible review output into a strict internal decision and receipt metadata."""
    raw = text if isinstance(text, str) else str(text)
    last_error = "review output did not contain a supported semantic result"
    for source, candidate in _json_candidates(raw):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        try:
            canonical, inferred, warnings = _canonicalize_mapping(data, reviewer_id, reviewer_type, story_id, chapter)
        except ValueError as exc:
            last_error = str(exc)
            continue
        if source == "json" and validate_review_decision(data, reviewer_id, reviewer_type, story_id, chapter) == []:
            source_format = "current_json"
            method = "current_json"
        elif source == "fenced_json":
            source_format = "fenced_json"
            method = "embedded_json"
        else:
            source_format = "legacy_json" if source == "json" else "embedded_json"
            method = "legacy_field_aliases"
        return {"canonical": canonical, "source_format": source_format, "normalization_method": method, "inferred_fields": inferred, "warnings": warnings}

    markdown = _markdown_mapping(raw)
    if markdown:
        try:
            canonical, inferred, warnings = _canonicalize_mapping(markdown, reviewer_id, reviewer_type, story_id, chapter)
        except ValueError as exc:
            last_error = str(exc)
        else:
            return {"canonical": canonical, "source_format": "current_markdown" if "## Issues" in raw else "legacy_markdown", "normalization_method": "markdown_fields", "inferred_fields": inferred, "warnings": warnings}

    prose = re.sub(r"^\s*```(?:markdown|md)?\s*|\s*```\s*$", "", raw.strip(), flags=re.IGNORECASE)
    lowered = prose.casefold()
    status = _status_value("blocked" if any(word in lowered for word in ("blocked", "unsafe", "cannot accept")) else "needs_revision" if any(word in lowered for word in ("needs revision", "revise", "rewrite required")) else "pass" if any(word in lowered for word in ("pass", "accept", "approved")) else "")
    if status and len(prose.split()) >= 8 and any(word in lowered for word in ("scene", "chapter", "paragraph", "opening", "ending", "character", "draft")):
        try:
            canonical, inferred, warnings = _canonicalize_mapping({"status": status, "summary": prose, "evidence": [{"location": "review output", "observation": prose, "reader_effect": "The reviewer supplied a chapter-specific assessment."}]}, reviewer_id, reviewer_type, story_id, chapter)
        except ValueError as exc:
            last_error = str(exc)
        else:
            inferred.extend(["status", "summary", "evidence"])
            return {"canonical": canonical, "source_format": "prose", "normalization_method": "semantic_prose", "inferred_fields": inferred, "warnings": warnings}

    if callable(semantic_normalizer):
        normalized_text = semantic_normalizer(raw, last_error)
        if isinstance(normalized_text, str) and normalized_text.strip() and normalized_text.strip() != raw.strip():
            receipt = normalize_review_decision(normalized_text, reviewer_id, reviewer_type, story_id, chapter, None)
            receipt["normalization_method"] = "configured_semantic_normalizer"
            receipt["warnings"] = [*receipt.get("warnings", []), last_error]
            receipt["inferred_fields"] = [*receipt.get("inferred_fields", []), "semantic_normalizer"]
            return receipt
    if "evidence" not in last_error.casefold():
        last_error = f"review output is ambiguous or lacks required evidence: {last_error}"
    raise ValueError(last_error)


normalize_review_output = normalize_review_decision
parse_flexible_review_decision = normalize_review_decision


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
    orchestration = provider.get("orchestration")
    delegation = session.get("delegation") if isinstance(session, dict) else None
    if orchestration == "codex_subagent":
        if provider["type"] != "codex_cli":
            errors.append("codex_subagent orchestration requires a codex_cli provider")
        if not isinstance(delegation, dict):
            errors.append("codex_subagent review requires delegation metadata")
        else:
            spawned = delegation["spawned_thread_ids"]
            completed = delegation["completed_thread_ids"]
            if len(spawned) != 1:
                errors.append("codex_subagent review requires exactly one spawned child")
            if spawned != completed:
                errors.append("codex_subagent spawned and completed child IDs must match")
            if isinstance(session, dict) and session.get("thread_id") in spawned:
                errors.append("codex_subagent child thread must differ from the parent thread")
    elif delegation is not None:
        errors.append("delegation metadata requires codex_subagent orchestration")
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
    return "\n".join(f"- {_markdown_scalar(value)}" for value in values) if values else "None."


def _markdown_scalar(value: Any) -> str:
    """Render canonical scalar content without allowing embedded report structure."""
    return re.sub(r"\s+", " ", str(value)).strip()


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
        _markdown_scalar(decision["summary"]),
        "## Evidence",
    ]
    for evidence in decision["evidence"]:
        lines.extend(
            [
                f"- Location: {_markdown_scalar(evidence['location'])}",
                f"  Observation: {_markdown_scalar(evidence['observation'])}",
                f"  Reader effect: {_markdown_scalar(evidence['reader_effect'])}",
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
                f"issue_type: {_markdown_scalar(issue['issue_type'])}",
                f"severity: {_markdown_scalar(issue['severity'])}",
                f"location: {_markdown_scalar(issue['location'])}",
                f"observation: {_markdown_scalar(issue['observation'])}",
                f"reader_effect: {_markdown_scalar(issue['reader_effect'])}",
                f"review_scope: {_markdown_scalar(issue['review_scope'])}",
                f"rewrite_required: {'yes' if issue['rewrite_required'] else 'no'}",
                f"rewrite_scope: {_markdown_scalar(issue['rewrite_scope'])}",
                f"suggested_fix: {_markdown_scalar(issue['suggested_fix'])}",
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
        delegation = session.get("delegation") if isinstance(session, dict) else None
        child_ids = (
            ", ".join(delegation.get("completed_thread_ids", []))
            if isinstance(delegation, dict)
            else "none"
        )
        lines.extend(
            [
                "## Runtime Provenance",
                f"- Model Profile: {provider.get('model_profile')}",
                f"- Provider: {provider.get('id')}",
                f"- Provider Type: {provider.get('type')}",
                f"- Codex Profile: {provider.get('codex_profile') or 'none'}",
                f"- Model: {provider.get('model') or 'unspecified'}",
                f"- Reasoning Effort: {provider.get('reasoning_effort') or 'unspecified'}",
                f"- Orchestration: {provider.get('orchestration') or 'direct'}",
                f"- Session Start: {session.get('start_mode', 'stateless')}",
                f"- Session Retention: {session.get('retention', 'none')}",
                f"- Thread ID: {session.get('thread_id') or 'none'}",
                f"- Subagent Thread IDs: {child_ids}",
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
