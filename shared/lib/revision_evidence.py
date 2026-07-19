"""Track required review issues across a prose revision and fresh review."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from shared.lib.review_parser import parse_review_run_record


RECEIPT_FILENAME = "revision_issue_receipt.json"


def revision_receipt_path(story_path: Path, chapter: int) -> Path:
    """Return the current machine-readable revision issue receipt path."""
    return story_path / "reviews" / "chapter" / f"{chapter:03d}" / RECEIPT_FILENAME


def collect_required_revision_issues(
    story_path: Path,
    story_id: str,
    chapter: int,
    source_draft_sha256: str,
) -> list[dict[str, Any]]:
    """Collect rewrite-required issues from canonical records for the source draft."""
    review_root = story_path / "reviews" / "chapter" / f"{chapter:03d}"
    required_by_key: dict[str, dict[str, Any]] = {}
    previous_receipt = load_revision_receipt(story_path, story_id, chapter)
    if previous_receipt is not None and previous_receipt["revised_draft_sha256"] == source_draft_sha256:
        required_by_key.update(
            {str(issue["key"]): issue for issue in previous_receipt["required_issues"]}
        )
    for layer in ("standard", "series", "special"):
        for path in sorted(review_root.glob(f"{layer}.*.json")):
            try:
                record = parse_review_run_record(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise RuntimeError(f"canonical review record is invalid: {path.name}: {exc}") from exc
            decision = record["decision"]
            reviewer = record["reviewer"]
            if (
                record["draft_sha256"] != source_draft_sha256
                or decision["story_id"] != story_id
                or decision["chapter"] != chapter
                or reviewer["type"] != layer
            ):
                continue
            for issue in decision["issues"]:
                if not issue["rewrite_required"]:
                    continue
                issue_id = str(issue["issue_id"])
                key = f"{reviewer['type']}.{reviewer['id']}:{issue_id}"
                required_by_key[key] = {
                    "key": key,
                    "reviewer": {"id": reviewer["id"], "type": reviewer["type"]},
                    "issue_id": issue_id,
                    "issue_type": issue["issue_type"],
                    "severity": issue["severity"],
                    "location": issue["location"],
                    "observation": issue["observation"],
                    "reader_effect": issue["reader_effect"],
                    "rewrite_scope": issue["rewrite_scope"],
                    "suggested_fix": issue["suggested_fix"],
                }
    return [required_by_key[key] for key in sorted(required_by_key)]


def build_revision_receipt(
    story_id: str,
    chapter: int,
    run_id: str,
    source_draft_sha256: str,
    revised_draft_sha256: str,
    required_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the durable link between source comments and revised prose."""
    return {
        "schema_version": 1,
        "story_id": story_id,
        "chapter": chapter,
        "revision_run_id": run_id,
        "source_draft_sha256": source_draft_sha256,
        "revised_draft_sha256": revised_draft_sha256,
        "required_issues": required_issues,
    }


def load_revision_receipt(story_path: Path, story_id: str, chapter: int) -> dict[str, Any] | None:
    """Load and minimally validate the current revision issue receipt."""
    path = revision_receipt_path(story_path, chapter)
    if not path.exists():
        return None
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"revision issue receipt is invalid: {exc}") from exc
    if not isinstance(receipt, dict):
        raise RuntimeError("revision issue receipt must contain an object")
    expected = {
        "schema_version": 1,
        "story_id": story_id,
        "chapter": chapter,
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise RuntimeError(f"revision issue receipt {field} must be {value!r}")
    if not isinstance(receipt.get("revision_run_id"), str) or not receipt["revision_run_id"].strip():
        raise RuntimeError("revision issue receipt revision_run_id is missing")
    for field in ("source_draft_sha256", "revised_draft_sha256"):
        if not isinstance(receipt.get(field), str) or not re.fullmatch(r"[a-f0-9]{64}", receipt[field]):
            raise RuntimeError(f"revision issue receipt {field} must be a SHA-256 hash")
    issues = receipt.get("required_issues")
    if not isinstance(issues, list):
        raise RuntimeError("revision issue receipt required_issues must be a list")
    for index, issue in enumerate(issues):
        if not isinstance(issue, dict):
            raise RuntimeError(f"revision issue receipt issue {index} must be an object")
        reviewer = issue.get("reviewer")
        if (
            not isinstance(reviewer, dict)
            or reviewer.get("type") not in {"standard", "series", "special"}
            or not isinstance(reviewer.get("id"), str)
            or not isinstance(issue.get("issue_id"), str)
            or not isinstance(issue.get("key"), str)
        ):
            raise RuntimeError(f"revision issue receipt issue {index} has invalid reviewer identity")
    return receipt


def prior_issues_for_reviewer(
    receipt: dict[str, Any] | None,
    draft_sha256: str,
    layer: str,
    reviewer_id: str,
) -> list[dict[str, Any]]:
    """Return prior issues that this reviewer must explicitly disposition."""
    if receipt is None or receipt["revised_draft_sha256"] != draft_sha256:
        return []
    return [
        issue
        for issue in receipt["required_issues"]
        if issue["reviewer"] == {"id": reviewer_id, "type": layer}
    ]


def revision_resolution_status(
    story_path: Path,
    story_id: str,
    chapter: int,
    draft_sha256: str,
) -> tuple[str, list[str]]:
    """Verify that each prior required issue was explicitly cleared by its reviewer."""
    receipt = load_revision_receipt(story_path, story_id, chapter)
    if receipt is None or receipt["revised_draft_sha256"] != draft_sha256:
        return "not_required", []
    required = receipt["required_issues"]
    if not required:
        return "not_required", []

    unresolved: list[str] = []
    review_root = story_path / "reviews" / "chapter" / f"{chapter:03d}"
    for prior in required:
        reviewer = prior["reviewer"]
        record_path = review_root / f"{reviewer['type']}.{reviewer['id']}.json"
        if not record_path.exists():
            unresolved.append(str(prior["key"]))
            continue
        try:
            record = parse_review_run_record(record_path.read_text(encoding="utf-8"))
        except ValueError:
            unresolved.append(str(prior["key"]))
            continue
        decision = record["decision"]
        if (
            record["draft_sha256"] != draft_sha256
            or record["reviewer"] != reviewer
            or decision["story_id"] != story_id
            or decision["chapter"] != chapter
        ):
            unresolved.append(str(prior["key"]))
            continue
        issue_id = str(prior["issue_id"])
        marker = f"resolved_prior_issue:{issue_id}"
        still_open = any(
            issue["issue_id"] == issue_id and issue["rewrite_required"]
            for issue in decision["issues"]
        )
        if marker not in decision["reviewer_notes"] or still_open:
            unresolved.append(str(prior["key"]))
    return ("pass", []) if not unresolved else ("incomplete", unresolved)
