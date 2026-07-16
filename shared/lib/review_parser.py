"""Parse lightweight structured review reports."""
from __future__ import annotations

import re


SEVERITIES = ("blocker", "major", "minor", "note")


def count_severities(text: str) -> dict[str, int]:
    """Count severity labels in review text."""
    counts = {severity: 0 for severity in SEVERITIES}
    for severity in SEVERITIES:
        counts[severity] = len(re.findall(rf"^\s*severity:\s*{severity}\s*$", text, flags=re.IGNORECASE | re.MULTILINE))
        listed = re.findall(rf"^\s*-\s*{severity}:\s*(\d+)", text, flags=re.IGNORECASE | re.MULTILINE)
        if listed:
            counts[severity] = max(counts[severity], sum(int(value) for value in listed))
    return counts


def has_required_major_rewrite(text: str) -> bool:
    """Return True when a major issue requires rewriting."""
    issue_blocks = re.split(r"^###\s+Issue\s+", text, flags=re.MULTILINE)
    return any(
        re.search(r"severity:\s*major", block, flags=re.IGNORECASE)
        and re.search(r"rewrite_required:\s*yes", block, flags=re.IGNORECASE)
        for block in issue_blocks
    )


def recommended_gate_status(text: str) -> str:
    """Derive a fail-closed gate status from an evidence-bearing review report."""
    lowered = text.lower()
    if "status: blocked" in lowered or "severity: blocker" in lowered:
        return "blocked"
    counts = count_severities(text)
    if "status: needs_revision" in lowered or "gate_status: revise" in lowered or counts["major"]:
        return "revise"
    if "status: pass" in lowered and "gate_status: accept" in lowered and "## evidence" in lowered:
        return "accepted"
    return "blocked"
