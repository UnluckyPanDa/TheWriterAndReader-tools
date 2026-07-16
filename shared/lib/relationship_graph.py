"""Load, validate, normalize, and summarize structured relationship canon."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from shared.lib.yaml_utils import load_yaml_text


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "relationship_graph.schema.json"


def load_relationship_graph(story_path: str | Path) -> dict[str, Any]:
    """Load and validate a story relationship graph."""
    root = Path(story_path).expanduser().resolve(strict=False)
    graph_path = root / "canon" / "relationship_graph.yaml"
    if not graph_path.exists():
        raise FileNotFoundError(
            f"relationship graph not found: {graph_path}; run 'twr wizard relation-plot init' first"
        )
    data = load_yaml_text(graph_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"relationship graph must contain a mapping: {graph_path}")
    validate_relationship_graph(data)
    return normalize_relationship_graph(data)


def validate_relationship_graph(data: dict[str, Any]) -> None:
    """Validate schema rules plus cross-references and visibility ranges."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda error: list(error.path))
    issues = [f"{_error_path(error.path)}: {error.message}" for error in errors]

    characters = data.get("characters") if isinstance(data.get("characters"), list) else []
    relationships = data.get("relationships") if isinstance(data.get("relationships"), list) else []
    character_ids = [item.get("id") for item in characters if isinstance(item, dict) and isinstance(item.get("id"), str) and item.get("id")]
    relationship_ids = [item.get("id") for item in relationships if isinstance(item, dict) and isinstance(item.get("id"), str) and item.get("id")]

    issues.extend(_duplicate_issues(character_ids, "character"))
    issues.extend(_duplicate_issues(relationship_ids, "relationship"))
    known_characters = set(character_ids)
    for index, relationship in enumerate(relationships):
        if not isinstance(relationship, dict):
            continue
        source = relationship.get("source")
        target = relationship.get("target")
        if isinstance(source, str) and source and source not in known_characters:
            issues.append(f"relationships[{index}].source: unknown character '{source}'")
        if isinstance(target, str) and target and target not in known_characters:
            issues.append(f"relationships[{index}].target: unknown character '{target}'")
        visibility = relationship.get("visibility")
        if isinstance(visibility, dict):
            start = visibility.get("start_chapter")
            end = visibility.get("end_chapter")
            if type(start) is int and type(end) is int and end < start:
                issues.append(f"relationships[{index}].visibility: end_chapter must be at least start_chapter")

    if issues:
        raise ValueError("Invalid relationship graph:\n" + "\n".join(f"- {issue}" for issue in issues))


def normalize_relationship_graph(data: dict[str, Any]) -> dict[str, Any]:
    """Return renderer-ready graph data with stable defaults and coordinates."""
    characters: list[dict[str, Any]] = []
    source_characters = data.get("characters", [])
    count = max(1, len(source_characters))
    for index, raw in enumerate(source_characters):
        character = dict(raw)
        angle = (2 * math.pi * index) / count
        position = character.get("position")
        if not isinstance(position, dict):
            position = {
                "x": round(math.cos(angle) * 180, 3),
                "y": round(((index % 5) - 2) * 42, 3),
                "z": round(math.sin(angle) * 180, 3),
            }
        character["position"] = position
        character.setdefault("group", "Ungrouped")
        character.setdefault("role", "")
        character.setdefault("status", "active")
        character.setdefault("color", _group_color(str(character["group"])))
        characters.append(character)

    relationships: list[dict[str, Any]] = []
    for raw in data.get("relationships", []):
        relationship = dict(raw)
        relationship.setdefault("strength", 0.5)
        relationship.setdefault("direction", "bidirectional")
        relationship.setdefault("color", "#90a4c3")
        relationship.setdefault("visibility", {"start_chapter": 1, "end_chapter": None})
        relationship.setdefault("notes", "")
        relationships.append(relationship)

    return {"version": 1, "characters": characters, "relationships": relationships}


def relationship_graph_summary(story_path: str | Path, chapter: int) -> str:
    """Build compact, chapter-visible relationship context for writing and review packs."""
    graph_path = Path(story_path) / "canon" / "relationship_graph.yaml"
    if not graph_path.exists():
        return "No structured relationship graph is configured."
    graph = load_relationship_graph(story_path)
    labels = {character["id"]: character["label"] for character in graph["characters"]}
    visible = [edge for edge in graph["relationships"] if _visible_in_chapter(edge, chapter)]
    if not visible:
        return f"No structured relationships are visible in chapter {chapter}."
    lines = []
    for edge in visible:
        arrow = {"outgoing": "->", "incoming": "<-", "bidirectional": "<->"}[edge["direction"]]
        note = f"; {edge['notes']}" if edge["notes"] else ""
        lines.append(
            f"- {labels[edge['source']]} {arrow} {labels[edge['target']]}: "
            f"{edge['type']} (strength {edge['strength']}){note}"
        )
    return "\n".join(lines)


def _visible_in_chapter(relationship: dict[str, Any], chapter: int) -> bool:
    visibility = relationship.get("visibility") or {}
    start = visibility.get("start_chapter") or 1
    end = visibility.get("end_chapter")
    return chapter >= start and (end is None or chapter <= end)


def _duplicate_issues(values: list[str], label: str) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return [f"duplicate {label} id '{value}'" for value in duplicates]


def _error_path(path: Any) -> str:
    parts = list(path)
    if not parts:
        return "graph"
    output = ""
    for part in parts:
        output += f"[{part}]" if isinstance(part, int) else ("." if output else "") + str(part)
    return output


def _group_color(group: str) -> str:
    palette = ["#70d6ff", "#ff70a6", "#ff9770", "#ffd670", "#8bf0a7", "#b8a1ff"]
    return palette[sum(ord(char) for char in group) % len(palette)]
