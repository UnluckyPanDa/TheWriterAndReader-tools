"""Generate chapter drafts for external story workspaces."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from shared.lib.config_loader import load_config
from shared.lib.model_router import attempt_model_chain, select_model_for_stage
from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.run_provenance import require_explicit_runtime_config, write_run_provenance
from shared.lib.safe_write import safe_write_file
from shared.lib.story_loader import load_markdown_file, load_story_context_file, load_story_yaml
from shared.lib.workspace_loader import resolve_story_path
from tools.writing.build_write_pack import build_write_pack


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


def build_generation_prompt(workspace_path: str | Path, story_id: str, chapter: int) -> str:
    """Build the model prompt from the current write pack."""
    story_path = resolve_story_path(workspace_path, story_id)
    story_yaml = load_story_yaml(story_path)
    language = story_language(story_yaml)
    title = str(story_yaml.get("title") or story_id)
    write_pack = load_story_context_file(story_path, "write_pack.md")
    if not write_pack.strip():
        write_pack = build_write_pack(str(workspace_path), story_id, chapter).read_text(encoding="utf-8")

    prior_drafts: list[str] = []
    for prior in range(max(1, chapter - 2), chapter):
        draft = load_markdown_file(story_path / "drafts" / f"chapter_{prior:03d}.md")
        if draft.strip():
            prior_drafts.append(f"### Chapter {prior} Sample\n" + "\n".join(draft.splitlines()[:80]))

    style_reference = "\n\n".join(prior_drafts) or "No prior draft sample is available."
    heading = chapter_heading(chapter, language)
    return f"""You are drafting a fiction chapter for "{title}".

Task: write chapter {chapter} in {language}.

## Write Pack
{write_pack}

## Prior Draft Style Reference
Use these samples only for local voice continuity. Do not copy sentences.

{style_reference}

## Draft Requirements
- Follow the story language exactly: {language}.
- Treat the canon, character files, timeline, and reveal lock as private constraints, not source prose. Use them to control truth, knowledge, desire, continuity, and forbidden reveals; do not copy or paraphrase their wording.
- Prioritize the current chapter task, then viewpoint character desire and resistance, then concrete actions and consequences, then only the continuity facts needed for this chapter.
- Do not reveal locked information.
- Do not make canon changes.
- Write a sequence of lived events in finished novel prose, not a plot summary, outline, canon explanation, or reviewer response.
- Each scene must have an immediate goal, resistance, a concrete action or choice, and a visible change in the situation.
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
    prompt = build_generation_prompt(workspace_path, story_id, chapter)
    chain = select_model_for_stage(config, "chapter_generation")
    result = attempt_model_chain(prompt, chain, config, options)
    if not result.get("ok"):
        attempts = result.get("attempts", [])
        raise RuntimeError(f"draft generation failed for all configured models: {attempts}")

    heading = chapter_heading(chapter, story_language(story_yaml))
    draft_text = normalize_generated_draft(str(result.get("text", "")), heading)
    output_path = story_path / "drafts" / f"chapter_{chapter:03d}.md"
    assert_story_write_allowed(output_path, story_path)
    saved_path = safe_write_file(output_path, draft_text + "\n", story_path)
    write_run_provenance(
        story_path,
        chapter,
        "generation",
        result,
        config,
        {"draft": str(saved_path.relative_to(story_path))},
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
