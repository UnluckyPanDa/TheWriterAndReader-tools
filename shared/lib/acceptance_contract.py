"""Validate and render grounded accepted-chapter continuity artifacts."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"
ACCEPTED_CONTINUITY_SCHEMA_PATH = SCHEMA_ROOT / "accepted_continuity.schema.json"
ACCEPTANCE_GROUNDING_SCHEMA_PATH = SCHEMA_ROOT / "acceptance_grounding.schema.json"


@lru_cache(maxsize=2)
def _validator(path: Path) -> Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _parse(text: str, path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    errors = sorted(_validator(path).iter_errors(data), key=lambda item: list(item.absolute_path))
    if errors:
        messages = []
        for error in errors[:8]:
            location = ".".join(str(part) for part in error.absolute_path) or "root"
            messages.append(f"{location}: {error.message}")
        raise ValueError(f"invalid {label}: " + "; ".join(messages))
    return data


def parse_accepted_continuity(text: str, story_id: str, chapter: int) -> dict[str, Any]:
    data = _parse(text, ACCEPTED_CONTINUITY_SCHEMA_PATH, "accepted continuity")
    if data["story_id"] != story_id:
        raise ValueError(f"accepted continuity story_id must be {story_id}")
    if data["chapter"] != chapter:
        raise ValueError(f"accepted continuity chapter must be {chapter}")
    for group_name in ("summary", "handover"):
        for field_name, values in data[group_name].items():
            if any(not value.strip() for value in values):
                raise ValueError(f"accepted continuity {group_name}.{field_name} cannot contain blank values")
    return data


def parse_acceptance_grounding(text: str, story_id: str, chapter: int) -> dict[str, Any]:
    data = _parse(text, ACCEPTANCE_GROUNDING_SCHEMA_PATH, "acceptance grounding decision")
    if data["story_id"] != story_id:
        raise ValueError(f"acceptance grounding story_id must be {story_id}")
    if data["chapter"] != chapter:
        raise ValueError(f"acceptance grounding chapter must be {chapter}")
    for field_name in ("unsupported_claims", "name_conflicts"):
        if any(not value.strip() for value in data[field_name]):
            raise ValueError(f"acceptance grounding {field_name} cannot contain blank values")
    expected_grounded = not (
        data["unsupported_claims"]
        or data["name_conflicts"]
        or data["thinking_trace_detected"]
    )
    if data["grounded"] != expected_grounded:
        raise ValueError("acceptance grounding grounded flag conflicts with its findings")
    return data


def render_accepted_continuity(data: dict[str, Any]) -> tuple[str, str]:
    chapter = int(data["chapter"])

    def section(title: str, values: list[str]) -> str:
        rows = "\n".join(f"- {value.strip()}" for value in values) or "- None recorded."
        return f"## {title}\n\n{rows}"

    summary = "\n\n".join(
        [
            f"# Chapter {chapter:03d} Accepted Summary",
            section("Events", data["summary"]["events"]),
            section("Decisions", data["summary"]["decisions"]),
            section("Discoveries", data["summary"]["discoveries"]),
            section("Relationship Changes", data["summary"]["relationship_changes"]),
            section("Practical State", data["summary"]["practical_state"]),
            section("Unresolved Pressure", data["summary"]["unresolved_pressure"]),
        ]
    ) + "\n"
    handover = "\n\n".join(
        [
            "# Story Handover",
            section("Ending Situation", data["handover"]["ending_situation"]),
            section("Character Intentions", data["handover"]["character_intentions"]),
            section("Relationship State", data["handover"]["relationship_state"]),
            section("Open Pressure", data["handover"]["open_pressure"]),
            section("Reader Questions", data["handover"]["reader_questions"]),
            section("Continuity Details", data["handover"]["continuity_details"]),
        ]
    ) + "\n"
    return summary, handover
