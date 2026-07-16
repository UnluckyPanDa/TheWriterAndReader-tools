"""Explicit scene planning, drafting, and chapter assembly commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from shared.lib.config_loader import load_config
from shared.lib.model_router import attempt_model_chain, select_model_for_stage
from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.run_provenance import require_explicit_runtime_config, write_run_provenance
from shared.lib.safe_write import safe_write_file
from shared.lib.scene_contract import parse_scene_contract
from shared.lib.scene_skeleton import parse_scene_skeleton
from shared.lib.story_loader import load_story_yaml
from shared.lib.workspace_loader import resolve_story_path
from tools.writing.build_write_pack import build_write_pack, write_pack_token_counts
from tools.writing.generate_draft import (
    _normalize_scene_draft,
    build_scene_generation_prompt,
    chapter_heading,
    generate_scene_contract,
    generate_scene_skeleton,
    story_language,
)


def _plan_paths(story_path: Path, chapter: int) -> tuple[Path, Path]:
    context = story_path / "context"
    return (
        context / f"chapter_{chapter:03d}_scene_contract.json",
        context / f"chapter_{chapter:03d}_scene_skeleton.json",
    )


def plan_scenes(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    config_path: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Generate and persist the reusable scene contract and skeleton."""
    story_path = resolve_story_path(workspace_path, story_id)
    config = load_config(config_path)
    require_explicit_runtime_config(config, "scene planning")
    write_pack_path = build_write_pack(str(workspace_path), story_id, chapter)
    write_pack = write_pack_path.read_text(encoding="utf-8")
    contract, contract_result = generate_scene_contract(config, story_id, chapter, write_pack, options)
    skeleton, skeleton_result = generate_scene_skeleton(config, story_id, chapter, contract, options)
    contract_path, skeleton_path = _plan_paths(story_path, chapter)
    for path, payload in ((contract_path, contract), (skeleton_path, skeleton)):
        assert_story_write_allowed(path, story_path)
        safe_write_file(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n", story_path)
    write_run_provenance(
        story_path,
        chapter,
        "scene_planning",
        {
            "model_profile": skeleton_result.get("model_profile"),
            "attempts": [*contract_result.get("attempts", []), *skeleton_result.get("attempts", [])],
        },
        config,
        {
            "scene_contract": str(contract_path.relative_to(story_path)),
            "scene_skeleton": str(skeleton_path.relative_to(story_path)),
            "write_pack": str(write_pack_path.relative_to(story_path)),
        },
        {
            "stages": ["scene_planning", "scene_skeleton"],
            "context_tokens_by_category": write_pack_token_counts(write_pack),
        },
    )
    return {"scene_contract": contract_path, "scene_skeleton": skeleton_path}


def load_scene_plan(story_path: Path, story_id: str, chapter: int) -> tuple[dict[str, Any], dict[str, Any]]:
    contract_path, skeleton_path = _plan_paths(story_path, chapter)
    if not contract_path.exists() or not skeleton_path.exists():
        raise FileNotFoundError("scene plan is missing; run `twr write plan-scene` first")
    contract = parse_scene_contract(contract_path.read_text(encoding="utf-8"), story_id, chapter)
    scene_ids = [str(scene["scene_id"]) for scene in contract["scenes"]]
    skeleton = parse_scene_skeleton(skeleton_path.read_text(encoding="utf-8"), story_id, chapter, scene_ids)
    return contract, skeleton


def draft_scene(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    scene_id: str,
    config_path: str | None = None,
    options: dict[str, Any] | None = None,
) -> Path:
    """Draft one planned scene into the chapter scene-draft directory."""
    story_path = resolve_story_path(workspace_path, story_id)
    contract, skeleton = load_scene_plan(story_path, story_id, chapter)
    contract_by_id = {str(scene["scene_id"]): scene for scene in contract["scenes"]}
    skeleton_by_id = {str(scene["scene_id"]): scene for scene in skeleton["scenes"]}
    if scene_id not in contract_by_id:
        raise ValueError(f"unknown scene_id: {scene_id}")
    config = load_config(config_path)
    require_explicit_runtime_config(config, "scene drafting")
    story_yaml = load_story_yaml(story_path)
    language = story_language(story_yaml)
    write_pack_path = build_write_pack(str(workspace_path), story_id, chapter)
    write_pack = write_pack_path.read_text(encoding="utf-8")
    scene_index = [str(scene["scene_id"]) for scene in contract["scenes"]].index(scene_id)
    continuity = "This is the first scene in the chapter."
    if scene_index:
        previous = contract["scenes"][scene_index - 1]
        continuity = f"Previous planned ending turn: {previous['ending_turn']}"
    result = attempt_model_chain(
        build_scene_generation_prompt(
            story_id,
            chapter,
            language,
            contract_by_id[scene_id],
            skeleton_by_id[scene_id],
            write_pack,
            continuity,
        ),
        select_model_for_stage(config, "chapter_generation"),
        config,
        options,
    )
    if not result.get("ok"):
        raise RuntimeError(f"scene draft failed for all configured models: {result.get('attempts', [])}")
    text = _normalize_scene_draft(str(result.get("text", "")))
    output_path = story_path / "drafts" / f"chapter_{chapter:03d}_scenes" / f"{scene_id}.md"
    assert_story_write_allowed(output_path, story_path)
    saved_path = safe_write_file(output_path, text.rstrip() + "\n", story_path)
    write_run_provenance(
        story_path,
        chapter,
        f"scene_{scene_id}_draft",
        result,
        config,
        {"scene_draft": str(saved_path.relative_to(story_path))},
        {"run_id": str(uuid4()), "scene_id": scene_id},
    )
    return saved_path


def assemble_chapter(workspace_path: str | Path, story_id: str, chapter: int) -> Path:
    """Assemble every planned scene draft in contract order."""
    story_path = resolve_story_path(workspace_path, story_id)
    contract, _ = load_scene_plan(story_path, story_id, chapter)
    scene_root = story_path / "drafts" / f"chapter_{chapter:03d}_scenes"
    scene_texts: list[str] = []
    missing: list[str] = []
    for scene in contract["scenes"]:
        scene_id = str(scene["scene_id"])
        path = scene_root / f"{scene_id}.md"
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            missing.append(scene_id)
        else:
            scene_texts.append(path.read_text(encoding="utf-8").strip())
    if missing:
        raise FileNotFoundError("missing scene drafts: " + ", ".join(missing))
    language = story_language(load_story_yaml(story_path))
    text = chapter_heading(chapter, language) + "\n\n" + "\n\n".join(scene_texts) + "\n"
    output_path = story_path / "drafts" / f"chapter_{chapter:03d}.md"
    assert_story_write_allowed(output_path, story_path)
    return safe_write_file(output_path, text, story_path)
