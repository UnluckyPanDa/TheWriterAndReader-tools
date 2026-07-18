"""Generate chapter drafts for external story workspaces."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from shared.lib.config_loader import load_config
from shared.lib.model_router import attempt_model_chain, attempt_structured_model_chain, select_model_for_stage
from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.run_provenance import require_explicit_runtime_config, write_run_provenance
from shared.lib.scene_contract import SCHEMA_PATH as SCENE_CONTRACT_SCHEMA_PATH, parse_scene_contract
from shared.lib.scene_skeleton import SCHEMA_PATH as SCENE_SKELETON_SCHEMA_PATH, parse_scene_skeleton
from shared.lib.safe_write import safe_write_file
from shared.lib.story_loader import load_markdown_file, load_story_yaml
from shared.lib.workspace_loader import resolve_story_path
from tools.writing.build_write_pack import build_write_pack, write_pack_token_counts
from tools.writing.diagnose import write_diagnostics


def story_language(story_yaml: dict[str, Any]) -> str:
    """Return the primary story language from supported story.yaml layouts."""
    language = story_yaml.get("language")
    if isinstance(language, str) and language.strip():
        return language.strip()
    if isinstance(language, dict):
        primary = language.get("primary")
        if isinstance(primary, str) and primary.strip():
            return primary.strip()
    return "en"


def chapter_number_to_chinese(number: int) -> str:
    """Convert common chapter numbers to compact Chinese numerals."""
    numerals = {
        1: "一",
        2: "二",
        3: "三",
        4: "四",
        5: "五",
        6: "六",
        7: "七",
        8: "八",
        9: "九",
        10: "十",
    }
    return numerals.get(number, str(number))


def chapter_heading(chapter: int, language: str) -> str:
    """Return the default Markdown heading for a chapter."""
    language_key = language.lower()
    if language_key.startswith("zh") or language_key in {"chinese", "mandarin"}:
        return f"# 第{chapter_number_to_chinese(chapter)}章"
    return f"# Chapter {chapter}"


def looks_like_chapter_heading(line: str) -> bool:
    """Detect common generated chapter headings."""
    return bool(re.match(r"^#?\s*(Chapter\s+\d+|第.+章)\b", line.strip(), re.IGNORECASE))


def normalize_generated_draft(text: str, heading: str) -> str:
    """Remove model preamble and enforce the configured chapter heading."""
    lines = text.strip().splitlines()
    if not lines:
        return heading

    start_index = 0
    for index, line in enumerate(lines):
        if looks_like_chapter_heading(line):
            start_index = index
            break
    chapter_text = "\n".join(lines[start_index:]).strip()

    if chapter_text.startswith(heading):
        return chapter_text

    chapter_lines = chapter_text.splitlines()
    for index, line in enumerate(chapter_lines[:5]):
        if looks_like_chapter_heading(line):
            chapter_lines[index] = heading
            return "\n".join(chapter_lines[index:]).strip()
    return f"{heading}\n\n{chapter_text}".strip()


def build_scene_contract_prompt(story_id: str, chapter: int, write_pack: str) -> str:
    """Build the planning prompt for a schema-validated scene contract."""
    return f"""Create the scene contract JSON for the requested fiction chapter.

story_id: {story_id}
chapter: {chapter}

## Write Pack
{write_pack}

## Scene Contract Rules
- Return only one JSON object with schema_version, story_id, chapter, chapter_progression, and scenes.
- chapter_progression needs concrete plot, character, and mystery movement.
- Every scene needs a unique scene_id, viewpoint_character, starting_state, immediate_goal, pressure, opposition, change_axes, required_change, new_information, physical_setting, active_characters, required_beats, forbidden_reveals, and ending_turn.
- change_axes may contain only: knowledge, emotion, relationship, practical_situation, danger, intention, mystery, access, commitment, reader_expectation.
- Every scene must change at least one axis and end in a materially different state.
- Preserve canon and reveal timing. Treat supplied wording as reference, not prose to copy.
- Do not include Markdown fences, commentary, or draft prose.

Return only the Scene Contract JSON.
"""


def _scene_contract_repair_prompt(
    story_id: str,
    chapter: int,
    invalid_text: str,
    validation_error: str,
) -> str:
    return f"""Repair the Scene Contract JSON so it satisfies the required contract.

story_id: {story_id}
chapter: {chapter}
validation_error: {validation_error}

## Invalid Output
{invalid_text}

Return only corrected Scene Contract JSON. Do not add prose or Markdown fences.
"""


def build_scene_skeleton_prompt(
    story_id: str,
    chapter: int,
    scene_contract: dict[str, Any],
) -> str:
    """Build the compact action-planning prompt for the prose pass."""
    return f"""Create the scene skeleton JSON for the requested fiction chapter.

story_id: {story_id}
chapter: {chapter}

## Validated Scene Contract
{json.dumps(scene_contract, ensure_ascii=False, indent=2)}

## Scene Skeleton Rules
- Return only one JSON object with schema_version, story_id, chapter, and scenes.
- Preserve every scene_id from the contract in the same order.
- Every scene needs purpose, entry_condition, action_sequence, conflict_escalation, emotional_turns, and exit_condition.
- Use concrete actions, reactions, interruptions, choices, and consequences.
- Make each action cause the next pressure or response.
- Preserve canon, required beats, required changes, and forbidden reveals.
- Do not write polished prose, dialogue, commentary, or Markdown fences.

Return only the Scene Skeleton JSON.
"""


def _scene_skeleton_repair_prompt(
    story_id: str,
    chapter: int,
    scene_contract: dict[str, Any],
    invalid_text: str,
    validation_error: str,
) -> str:
    return f"""Repair the Scene Skeleton JSON so it satisfies the required contract.

story_id: {story_id}
chapter: {chapter}
validation_error: {validation_error}

## Required Scene Contract
{json.dumps(scene_contract, ensure_ascii=False, indent=2)}

## Invalid Output
{invalid_text}

Return only corrected Scene Skeleton JSON. Do not add prose or Markdown fences.
"""


def build_generation_prompt(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    scene_contract: dict[str, Any] | None = None,
    scene_skeleton: dict[str, Any] | None = None,
    write_pack: str | None = None,
) -> str:
    """Build the model prompt from a fresh write pack and optional scene contract."""
    story_path = resolve_story_path(workspace_path, story_id)
    story_yaml = load_story_yaml(story_path)
    language = story_language(story_yaml)
    title = str(story_yaml.get("title") or story_id)
    if write_pack is None:
        write_pack = build_write_pack(str(workspace_path), story_id, chapter).read_text(encoding="utf-8")

    accepted_reference = "No previous accepted chapter is available."
    if chapter > 1:
        accepted = load_markdown_file(story_path / "chapters" / f"chapter_{chapter - 1:03d}.md")
        if accepted.strip():
            accepted_reference = "\n".join(accepted.strip().splitlines()[-40:])
    contract_text = json.dumps(scene_contract, ensure_ascii=False, indent=2) if scene_contract else "No scene contract supplied."
    skeleton_text = (
        json.dumps(scene_skeleton, ensure_ascii=False, indent=2)
        if scene_skeleton
        else "No scene skeleton supplied."
    )
    heading = chapter_heading(chapter, language)
    return f"""You are drafting a fiction chapter for "{title}".

Task: write chapter {chapter} in {language}.

## Write Pack
{write_pack}

## Validated Scene Contract
{contract_text}

## Validated Scene Skeleton
{skeleton_text}

## Previous Accepted Chapter Ending [SOURCE_TEXT]
Use this only for immediate state and local voice continuity. Do not copy its sentences.

{accepted_reference}

## Draft Requirements
- Follow the story language exactly: {language}.
- Treat the canon, character files, timeline, and reveal lock as private constraints, not source prose. Use them to control truth, knowledge, desire, continuity, and forbidden reveals; do not copy or paraphrase their wording.
- Prioritize the current chapter task, then viewpoint character desire and resistance, then concrete actions and consequences, then only the continuity facts needed for this chapter.
- Do not reveal locked information.
- Do not make canon changes.
- Write a sequence of lived events in finished novel prose, not a plot summary, outline, canon explanation, or reviewer response.
- Each scene must have an immediate goal, resistance, a concrete action or choice, and a visible change in the situation.
- Follow the validated scene contract in order. Do not invent scenes that bypass its required change or forbidden reveals.
- Follow the validated scene skeleton's causal action sequence. Expand it into lived prose without copying its planning language.
- Use close point of view: show only what the viewpoint character perceives, remembers, infers, or physically does. Let the reader infer themes and psychology from evidence.
- Use specific objects, positioning, interruptions, incomplete answers, socially constrained dialogue, and selective sensory details. Dialogue must pursue a character's immediate goal and change pressure or relationship.
- Do not label character traits, emotional states, themes, symbolism, or relationship dynamics in narration when observable behavior can show them.
- Avoid repeated canon terminology, abstract emotional labels, generic reactions, repeated gestures, and sentences that restate the previous paragraph's meaning.
- Keep technical explanation brief and make it create conflict, risk, or a decision.
- Begin inside an active situation. End after a concrete discovery, choice, interruption, or changed relationship; do not summarize the chapter afterward.
- Self-revise for scene movement, specific detail, sentence rhythm, emotional causality, and repetition before returning the draft.
- Do not include meta commentary, analysis, or author notes.
- Output only the chapter text, starting with this heading:

{heading}
"""


def build_polish_prompt(
    story_id: str,
    chapter: int,
    language: str,
    heading: str,
    scene_contract: dict[str, Any],
    first_draft: str,
    writer_voice: str = "",
) -> str:
    """Build a constrained compression and voice-polish prompt."""
    return f"""Polish this fiction chapter in {language}.

story_id: {story_id}
chapter: {chapter}

## Validated Scene Contract
{json.dumps(scene_contract, ensure_ascii=False, indent=2)}

## Writer Voice
{writer_voice.strip() or "Use the established voice of the supplied draft."}

## Draft To Polish
{first_draft}

## Polish Rules
- Preserve every event, character decision, reveal boundary, scene order, and ending turn.
- Do not add plot facts, characters, locations, objects, explanations, or dialogue exchanges.
- Remove repeated meanings, repeated emotional labels, canon restatement, planning language, generic reactions, and explanations already shown by action or dialogue.
- Improve viewpoint consistency, sentence-length variation, paragraph rhythm, dialogue spacing, transitions, and word repetition.
- Keep concrete actions, consequential sensory detail, social pressure, subtext, and causal links.
- Keep the chapter heading exactly as supplied.
- Return only the polished chapter text, starting with this heading:

{heading}
"""


def build_scene_generation_prompt(
    story_id: str,
    chapter: int,
    language: str,
    scene_contract: dict[str, Any],
    scene_skeleton: dict[str, Any],
    write_pack: str,
    continuity_entry: str,
) -> str:
    """Build a first-prose prompt for one validated scene."""
    return f"""Draft one fiction scene for story `{story_id}`, chapter {chapter}, in {language}.

## Active Write Pack
{write_pack}

## Scene Contract
{json.dumps(scene_contract, ensure_ascii=False, indent=2)}

## Scene Skeleton
{json.dumps(scene_skeleton, ensure_ascii=False, indent=2)}

## Continuity Entry
{continuity_entry}

## First Prose Pass Rules
- Write only this scene in finished novel prose, without a chapter heading or scene label.
- Follow the action sequence causally and complete every required beat and state change.
- Use physical action, character interaction, viewpoint-specific perception, concrete setting, and cause and effect.
- Keep explanation minimal. Dialogue must pursue an immediate goal and meet resistance.
- Preserve canon and forbidden reveals. Treat supplied planning wording as facts, not prose to copy.
- End on the specified exit condition and ending turn.
- Return only scene prose.
"""


def build_deepening_prompt(
    story_id: str,
    chapter: int,
    language: str,
    heading: str,
    scene_contract: dict[str, Any],
    draft: str,
) -> str:
    """Build the narrative-deepening pass prompt."""
    return f"""Deepen this fiction chapter for story `{story_id}`, chapter {chapter}, in {language}.

## Validated Scene Contract
{json.dumps(scene_contract, ensure_ascii=False, indent=2)}

## First Prose Draft
{draft}

## Narrative Deepening Rules
- Preserve events, scene order, decisions, reveal timing, and ending turns.
- Add only missing physical behavior, social pressure, selective sensory detail, subtext, interruption, meaningful object interaction, or emotional contradiction.
- Replace synopsis-like statements with lived action only where the scene contract requires the moment to land.
- Do not make sentences longer merely to add texture.
- Do not add facts, characters, objects, locations, backstory, or new dialogue topics.
- Return only the deepened chapter, starting with this exact heading:

{heading}
"""


def build_compression_prompt(
    story_id: str,
    chapter: int,
    language: str,
    heading: str,
    scene_contract: dict[str, Any],
    draft: str,
) -> str:
    """Build the compression and semantic de-duplication pass prompt."""
    return f"""Compress and de-duplicate this fiction chapter for story `{story_id}`, chapter {chapter}, in {language}.

## Validated Scene Contract
{json.dumps(scene_contract, ensure_ascii=False, indent=2)}

## Deepened Draft
{draft}

## Compression Rules
- Preserve every required beat, event, choice, consequence, reveal boundary, scene order, and ending turn.
- Remove repeated meanings, repeated emotion labels, duplicate metaphors, canon restatement, summary after dialogue, and explanations already demonstrated through action.
- Remove padding created by synonyms, repeated internal questions, generic sensory language, and minor movement without consequence.
- Do not add or replace plot content.
- Return only the compressed chapter, starting with this exact heading:

{heading}
"""


def _write_pack_section(write_pack: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", write_pack, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _normalize_scene_draft(text: str) -> str:
    lines = text.strip().splitlines()
    while lines and (looks_like_chapter_heading(lines[0]) or lines[0].strip().lower().startswith("scene ")):
        lines.pop(0)
    return "\n".join(lines).strip()


def generate_scene_contract(
    config: dict[str, Any],
    story_id: str,
    chapter: int,
    write_pack: str,
    options: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    chain = select_model_for_stage(config, "scene_planning", fallback_stage="chapter_generation")
    router_options = {
        **(options or {}),
        "output_schema_path": str(SCENE_CONTRACT_SCHEMA_PATH),
        "structured_output": True,
        "progress_label": "scene contract",
    }
    result = attempt_structured_model_chain(
        build_scene_contract_prompt(story_id, chapter, write_pack),
        chain,
        config,
        lambda text: parse_scene_contract(text, story_id, chapter),
        lambda text, error: _scene_contract_repair_prompt(story_id, chapter, text, error),
        router_options,
    )
    if not result.get("ok"):
        raise RuntimeError(f"scene planning failed for all configured models: {result.get('attempts', [])}")
    return result["value"], result


def generate_scene_skeleton(
    config: dict[str, Any],
    story_id: str,
    chapter: int,
    scene_contract: dict[str, Any],
    options: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    scene_ids = [str(scene["scene_id"]) for scene in scene_contract["scenes"]]
    chain = select_model_for_stage(config, "scene_skeleton", fallback_stage="chapter_generation")
    router_options = {
        **(options or {}),
        "output_schema_path": str(SCENE_SKELETON_SCHEMA_PATH),
        "structured_output": True,
        "progress_label": "scene skeleton",
    }
    result = attempt_structured_model_chain(
        build_scene_skeleton_prompt(story_id, chapter, scene_contract),
        chain,
        config,
        lambda text: parse_scene_skeleton(text, story_id, chapter, scene_ids),
        lambda text, error: _scene_skeleton_repair_prompt(
            story_id,
            chapter,
            scene_contract,
            text,
            error,
        ),
        router_options,
    )
    if not result.get("ok"):
        raise RuntimeError(f"scene skeleton planning failed for all configured models: {result.get('attempts', [])}")
    return result["value"], result


def generate_draft(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    config_path: str | None = None,
    options: dict[str, Any] | None = None,
) -> Path:
    """Generate and write a chapter draft, returning the draft path."""
    story_path = resolve_story_path(workspace_path, story_id)
    story_yaml = load_story_yaml(story_path)
    config = load_config(config_path)
    require_explicit_runtime_config(config, "chapter generation")
    write_pack_path = build_write_pack(str(workspace_path), story_id, chapter)
    write_pack = write_pack_path.read_text(encoding="utf-8")
    scene_contract, planning_result = generate_scene_contract(config, story_id, chapter, write_pack, options)
    scene_skeleton, skeleton_result = generate_scene_skeleton(config, story_id, chapter, scene_contract, options)
    language = story_language(story_yaml)
    heading = chapter_heading(chapter, language)
    accepted_entry = "No previous accepted chapter is available."
    if chapter > 1:
        accepted = load_markdown_file(story_path / "chapters" / f"chapter_{chapter - 1:03d}.md")
        if accepted.strip():
            accepted_entry = "\n".join(accepted.strip().splitlines()[-40:])

    chain = select_model_for_stage(config, "chapter_generation")
    skeleton_by_id = {scene["scene_id"]: scene for scene in scene_skeleton["scenes"]}
    scene_results: list[dict[str, Any]] = []
    scene_drafts: list[tuple[str, str]] = []
    continuity_entry = accepted_entry
    for scene in scene_contract["scenes"]:
        scene_id = str(scene["scene_id"])
        result = attempt_model_chain(
            build_scene_generation_prompt(
                story_id,
                chapter,
                language,
                scene,
                skeleton_by_id[scene_id],
                write_pack,
                continuity_entry,
            ),
            chain,
            config,
            {**(options or {}), "progress_label": f"scene draft {scene_id}"},
        )
        if not result.get("ok"):
            raise RuntimeError(
                f"scene draft {scene_id} failed for all configured models: {result.get('attempts', [])}"
            )
        scene_text = _normalize_scene_draft(str(result.get("text", "")))
        scene_results.append(result)
        scene_drafts.append((scene_id, scene_text))
        continuity_entry = f"Previous scene ending turn: {scene['ending_turn']}\nPrevious scene final prose:\n" + "\n".join(
            scene_text.splitlines()[-12:]
        )

    first_draft = heading + "\n\n" + "\n\n".join(text for _, text in scene_drafts)
    deepening_chain = select_model_for_stage(config, "narrative_deepening", fallback_stage="chapter_generation")
    deepening_result = attempt_model_chain(
        build_deepening_prompt(story_id, chapter, language, heading, scene_contract, first_draft),
        deepening_chain,
        config,
        {**(options or {}), "progress_label": "narrative deepening"},
    )
    if not deepening_result.get("ok"):
        raise RuntimeError(
            f"narrative deepening failed for all configured models: {deepening_result.get('attempts', [])}"
        )
    deepened_draft = normalize_generated_draft(str(deepening_result.get("text", "")), heading)
    compression_chain = select_model_for_stage(config, "de_duplication", fallback_stage="chapter_generation")
    compression_result = attempt_model_chain(
        build_compression_prompt(story_id, chapter, language, heading, scene_contract, deepened_draft),
        compression_chain,
        config,
        {**(options or {}), "progress_label": "compression and de-duplication"},
    )
    if not compression_result.get("ok"):
        raise RuntimeError(
            f"compression and de-duplication failed for all configured models: {compression_result.get('attempts', [])}"
        )
    compressed_draft = normalize_generated_draft(str(compression_result.get("text", "")), heading)
    polish_chain = select_model_for_stage(config, "prose_polish", fallback_stage="chapter_generation")
    polish_result = attempt_model_chain(
        build_polish_prompt(
            story_id,
            chapter,
            language,
            heading,
            scene_contract,
            compressed_draft,
            _write_pack_section(write_pack, "Writer Voice"),
        ),
        polish_chain,
        config,
        {**(options or {}), "progress_label": "prose polish"},
    )
    if not polish_result.get("ok"):
        attempts = polish_result.get("attempts", [])
        raise RuntimeError(f"prose polish failed for all configured models: {attempts}")
    draft_text = normalize_generated_draft(str(polish_result.get("text", "")), heading)
    run_id = str(uuid4())
    run_path = story_path / "runs" / f"chapter_{chapter:03d}" / run_id
    contract_path = run_path / "scene_contract.json"
    skeleton_path = run_path / "scene_skeleton.json"
    first_draft_path = run_path / "first_draft.md"
    deepened_draft_path = run_path / "deepened_draft.md"
    compressed_draft_path = run_path / "compressed_draft.md"
    for artifact_path, content in (
        (contract_path, json.dumps(scene_contract, ensure_ascii=False, indent=2) + "\n"),
        (skeleton_path, json.dumps(scene_skeleton, ensure_ascii=False, indent=2) + "\n"),
        (first_draft_path, first_draft + "\n"),
        (deepened_draft_path, deepened_draft + "\n"),
        (compressed_draft_path, compressed_draft + "\n"),
    ):
        assert_story_write_allowed(artifact_path, story_path)
        safe_write_file(artifact_path, content, story_path)
    scene_paths: dict[str, str] = {}
    for scene_id, scene_text in scene_drafts:
        scene_path = run_path / "scenes" / f"{scene_id}.md"
        assert_story_write_allowed(scene_path, story_path)
        safe_write_file(scene_path, scene_text.rstrip() + "\n", story_path)
        scene_paths[scene_id] = str(scene_path.relative_to(story_path))
    output_path = story_path / "drafts" / f"chapter_{chapter:03d}.md"
    assert_story_write_allowed(output_path, story_path)
    saved_path = safe_write_file(output_path, draft_text + "\n", story_path)
    diagnostics_path = write_diagnostics(
        workspace_path,
        story_id,
        chapter,
        run_path / "writing_diagnostics.json",
    )
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    write_run_provenance(
        story_path,
        chapter,
        "generation",
        {
            "model_profile": polish_result.get("model_profile"),
            "attempts": [
                *planning_result.get("attempts", []),
                *skeleton_result.get("attempts", []),
                *(attempt for result in scene_results for attempt in result.get("attempts", [])),
                *deepening_result.get("attempts", []),
                *compression_result.get("attempts", []),
                *polish_result.get("attempts", []),
            ],
        },
        config,
        {
            "draft": str(saved_path.relative_to(story_path)),
            "diagnostics": str(diagnostics_path.relative_to(story_path)),
            "first_draft": str(first_draft_path.relative_to(story_path)),
            "deepened_draft": str(deepened_draft_path.relative_to(story_path)),
            "compressed_draft": str(compressed_draft_path.relative_to(story_path)),
            "scene_drafts": scene_paths,
            "scene_contract": str(contract_path.relative_to(story_path)),
            "scene_skeleton": str(skeleton_path.relative_to(story_path)),
            "write_pack": str(write_pack_path.relative_to(story_path)),
        },
        {
            "run_id": run_id,
            "context_tokens_by_category": write_pack_token_counts(write_pack),
            "context_files_loaded": diagnostics.get("source_files_checked", []),
            "writing_metrics": diagnostics.get("metrics", {}),
            "generation_pass": "voice_polish_complete",
            "stages": [
                {"name": "scene_planning", "model_profile": planning_result.get("model_profile")},
                {"name": "scene_skeleton", "model_profile": skeleton_result.get("model_profile")},
                {
                    "name": "scene_first_drafts",
                    "model_profiles": [result.get("model_profile") for result in scene_results],
                },
                {"name": "narrative_deepening", "model_profile": deepening_result.get("model_profile")},
                {"name": "de_duplication", "model_profile": compression_result.get("model_profile")},
                {"name": "prose_polish", "model_profile": polish_result.get("model_profile")},
            ],
        },
    )
    return saved_path


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for direct module execution."""
    parser = argparse.ArgumentParser(description="Generate a chapter draft.")
    parser.add_argument("--workspace", required=True, help="Path to the external story workspace.")
    parser.add_argument("--story", required=True, help="Story id from workspace.yaml.")
    parser.add_argument("--chapter", required=True, type=int, help="Chapter number to draft.")
    parser.add_argument("--config", help="Optional external config path.")
    args = parser.parse_args(argv)

    output_path = generate_draft(args.workspace, args.story, args.chapter, args.config)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
