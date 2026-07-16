"""Parse and validate model-generated scene contracts."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "scene_contract.schema.json"


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _json_text(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped, re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return stripped


def parse_scene_contract(text: str, story_id: str, chapter: int) -> dict[str, Any]:
    """Return a validated scene contract or raise a concise ValueError."""
    try:
        data = json.loads(_json_text(text))
    except json.JSONDecodeError as exc:
        raise ValueError(f"scene contract is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("scene contract must be a JSON object")

    errors = sorted(_validator().iter_errors(data), key=lambda item: list(item.absolute_path))
    if errors:
        messages = []
        for error in errors[:5]:
            location = ".".join(str(part) for part in error.absolute_path) or "root"
            messages.append(f"{location}: {error.message}")
        raise ValueError("invalid scene contract: " + "; ".join(messages))
    if data["story_id"] != story_id:
        raise ValueError(f"scene contract story_id must be {story_id}")
    if data["chapter"] != chapter:
        raise ValueError(f"scene contract chapter must be {chapter}")

    text_fields = (
        "scene_id",
        "viewpoint_character",
        "starting_state",
        "immediate_goal",
        "pressure",
        "opposition",
        "required_change",
        "new_information",
        "physical_setting",
        "ending_turn",
    )
    for index, scene in enumerate(data["scenes"]):
        for field in text_fields:
            if not scene[field].strip():
                raise ValueError(f"scene contract scenes.{index}.{field} cannot be blank")
        for field in ("active_characters", "required_beats", "forbidden_reveals"):
            if any(not value.strip() for value in scene[field]):
                raise ValueError(f"scene contract scenes.{index}.{field} cannot contain blank values")

    scene_ids = [scene["scene_id"] for scene in data["scenes"]]
    if len(scene_ids) != len(set(scene_ids)):
        raise ValueError("scene contract scene_id values must be unique")
    return data
