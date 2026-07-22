"""Parse and validate model-generated scene contracts."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
import unicodedata

from jsonschema import Draft202012Validator


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "scene_contract.schema.json"

GENERIC_CHARACTER_LABELS = {
    "a character",
    "antagonist",
    "child",
    "colleague",
    "customer",
    "friend",
    "parent",
    "protagonist",
    "student",
    "supervisor",
    "teacher",
    "the antagonist",
    "the protagonist",
    "unknown person",
    "witness",
    "主角",
    "同事",
    "學生",
    "老師",
    "證人",
}

_CODE_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:[-_:/\.][A-Za-z0-9]+)+\b")
_NUMBER_PATTERN = re.compile(r"\d{2,}(?:[:./-]\d+)*")
_CHAPTER_PATTERN = re.compile(r"\b(?:chapter|part)\s+\d+\b", re.IGNORECASE)
_CAPITALIZED_PATTERN = re.compile(r"\b[A-Z][a-z]{2,}\b")
_COMMON_CAPITALIZED = {
    "After",
    "Before",
    "Chapter",
    "During",
    "Scene",
    "Their",
    "There",
    "These",
    "They",
    "This",
    "When",
    "Where",
    "While",
}


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


def _normalized(value: str) -> str:
    return re.sub(r"[^\w]+", "", unicodedata.normalize("NFKC", value).casefold())


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for entry in value for item in _string_values(entry)]
    if isinstance(value, dict):
        return [item for entry in value.values() for item in _string_values(entry)]
    return []


def _distinctive_anchors(value: Any) -> set[str]:
    anchors: set[str] = set()
    for text in _string_values(value):
        anchors.update(_CODE_PATTERN.findall(text))
        anchors.update(_NUMBER_PATTERN.findall(text))
        anchors.update(_CHAPTER_PATTERN.findall(text))
        words = _CAPITALIZED_PATTERN.findall(text)
        anchors.update(word for word in words[1:] if word not in _COMMON_CAPITALIZED)
    return anchors


def unsupported_planning_anchors(value: Any, grounding_source: str) -> list[str]:
    """Return distinctive names, codes, or numbers absent from the grounding source."""
    normalized_source = _normalized(grounding_source)
    return sorted(
        anchor
        for anchor in _distinctive_anchors(value)
        if _normalized(anchor) not in normalized_source
    )


def validate_scene_contract_grounding(data: dict[str, Any], write_pack: str) -> None:
    """Reject scene-plan identities and factual anchors absent from the active pack."""
    normalized_pack = _normalized(write_pack)
    unsupported_characters: set[str] = set()
    for scene in data["scenes"]:
        labels = [scene["viewpoint_character"], *scene["active_characters"]]
        for label in labels:
            normalized_label = _normalized(label)
            if label.casefold().strip() in GENERIC_CHARACTER_LABELS:
                continue
            if normalized_label not in normalized_pack:
                unsupported_characters.add(label)
    unsupported = unsupported_planning_anchors(
        {
            "chapter_progression": data["chapter_progression"],
            "scenes": [
                {
                    key: value
                    for key, value in scene.items()
                    if key not in {"scene_id", "change_axes"}
                }
                for scene in data["scenes"]
            ],
        },
        write_pack,
    )
    problems = [
        *[f"character:{label}" for label in sorted(unsupported_characters)],
        *[f"anchor:{anchor}" for anchor in unsupported],
    ]
    if problems:
        raise ValueError(
            "scene contract contains unsupported planning anchors: " + ", ".join(problems[:12])
        )


def parse_scene_contract(
    text: str,
    story_id: str,
    chapter: int,
    write_pack: str | None = None,
) -> dict[str, Any]:
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
    if write_pack is not None:
        validate_scene_contract_grounding(data, write_pack)
    return data


def normalize_scene_contract(
    text: str,
    story_id: str,
    chapter: int,
    write_pack: str | None = None,
) -> dict[str, Any]:
    """Normalize an understandable legacy or lightly structured scene plan."""
    try:
        raw = json.loads(_json_text(text))
    except json.JSONDecodeError as exc:
        raise ValueError(f"scene plan is not recognizable JSON: {exc.msg}") from exc
    if isinstance(raw, dict):
        nested = raw.get("scene_plan") or raw.get("plan") or raw.get("outline")
        if isinstance(nested, dict):
            raw = nested
    if not isinstance(raw, dict):
        raise ValueError("scene plan must be an object")
    if "story_id" in raw and raw["story_id"] != story_id:
        raise ValueError(f"scene plan story_id must be {story_id}")
    if "chapter" in raw and raw["chapter"] != chapter:
        raise ValueError(f"scene plan chapter must be {chapter}")
    raw_scenes = raw.get("scenes") or raw.get("steps") or raw.get("beats") or raw.get("acts")
    if isinstance(raw_scenes, dict):
        raw_scenes = list(raw_scenes.values())
    if isinstance(raw_scenes, str):
        raw_scenes = [raw_scenes]
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise ValueError("scene plan lacks understandable scenes")

    def text_value(item: Any, *keys: str, default: str) -> str:
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict):
            for key in keys:
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return default

    def list_value(item: Any, *keys: str, default: list[str]) -> list[str]:
        if isinstance(item, dict):
            for key in keys:
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return [value.strip()]
                if isinstance(value, list):
                    values = [str(entry).strip() for entry in value if str(entry).strip()]
                    if values:
                        return values
        return list(default)

    scenes: list[dict[str, Any]] = []
    for index, item in enumerate(raw_scenes, start=1):
        viewpoint = text_value(item, "viewpoint_character", "viewpoint", "character", "pov", default="protagonist")
        goal = text_value(item, "immediate_goal", "goal", "purpose", "objective", "description", default="Advance the active chapter task.")
        pressure = text_value(item, "pressure", "conflict", "obstacle", default="The situation resists an easy solution.")
        required_change = text_value(item, "required_change", "change", "consequence", "outcome", default="The immediate situation changes.")
        ending = text_value(item, "ending_turn", "ending", "turn", "exit_condition", default="The choice creates forward pressure.")
        scenes.append(
            {
                "scene_id": text_value(item, "scene_id", "id", "name", default=f"scene-{index}"),
                "viewpoint_character": viewpoint,
                "starting_state": text_value(item, "starting_state", "entry_condition", "entry", default="The chapter task remains unresolved."),
                "immediate_goal": goal,
                "pressure": pressure,
                "opposition": text_value(item, "opposition", "resistance", "obstacle", default=pressure),
                "change_axes": list_value(item, "change_axes", "axes", default=["practical_situation"]),
                "required_change": required_change,
                "new_information": text_value(item, "new_information", "discovery", "reveal", default="The action creates a consequential discovery."),
                "physical_setting": text_value(item, "physical_setting", "setting", "location", default="The active chapter setting."),
                "active_characters": list_value(item, "active_characters", "characters", default=[viewpoint]),
                "required_beats": list_value(item, "required_beats", "beats", "actions", default=[goal, required_change]),
                "forbidden_reveals": list_value(item, "forbidden_reveals", "forbidden", "reveal_lock", default=[]),
                "ending_turn": ending,
            }
        )
    normalized = {
        "schema_version": 1,
        "story_id": story_id,
        "chapter": chapter,
        "chapter_progression": {
            "plot": text_value(raw.get("chapter_progression", raw), "plot", "plot_progression", default="The chapter task changes the practical situation."),
            "character": text_value(raw.get("chapter_progression", raw), "character", "character_progression", default="The viewpoint character makes a consequential choice."),
            "mystery": text_value(raw.get("chapter_progression", raw), "mystery", "mystery_progression", default="The outcome creates forward pressure."),
        },
        "scenes": scenes,
    }
    return parse_scene_contract(json.dumps(normalized, ensure_ascii=False), story_id, chapter, write_pack)
