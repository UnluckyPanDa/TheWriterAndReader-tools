"""Parse and validate model-generated scene skeletons."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from shared.lib.scene_contract import _json_text, unsupported_planning_anchors


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "scene_skeleton.schema.json"


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def parse_scene_skeleton(
    text: str,
    story_id: str,
    chapter: int,
    scene_ids: list[str],
    scene_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a validated scene skeleton or raise a concise ValueError."""
    try:
        data = json.loads(_json_text(text))
    except json.JSONDecodeError as exc:
        raise ValueError(f"scene skeleton is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("scene skeleton must be a JSON object")

    errors = sorted(_validator().iter_errors(data), key=lambda item: list(item.absolute_path))
    if errors:
        messages = []
        for error in errors[:5]:
            location = ".".join(str(part) for part in error.absolute_path) or "root"
            messages.append(f"{location}: {error.message}")
        raise ValueError("invalid scene skeleton: " + "; ".join(messages))
    if data["story_id"] != story_id:
        raise ValueError(f"scene skeleton story_id must be {story_id}")
    if data["chapter"] != chapter:
        raise ValueError(f"scene skeleton chapter must be {chapter}")

    skeleton_ids = [scene["scene_id"] for scene in data["scenes"]]
    if skeleton_ids != scene_ids:
        raise ValueError("scene skeleton scene_id values must match the scene contract in order")
    for index, scene in enumerate(data["scenes"]):
        for field in ("scene_id", "purpose", "entry_condition", "exit_condition"):
            if not scene[field].strip():
                raise ValueError(f"scene skeleton scenes.{index}.{field} cannot be blank")
        for field in ("action_sequence", "conflict_escalation", "emotional_turns"):
            if any(not value.strip() for value in scene[field]):
                raise ValueError(f"scene skeleton scenes.{index}.{field} cannot contain blank values")
    if scene_contract is not None:
        unsupported = unsupported_planning_anchors(
            [
                {key: value for key, value in scene.items() if key != "scene_id"}
                for scene in data["scenes"]
            ],
            json.dumps(scene_contract, ensure_ascii=False),
        )
        if unsupported:
            raise ValueError(
                "scene skeleton contains unsupported planning anchors: "
                + ", ".join(unsupported[:12])
            )
    return data
