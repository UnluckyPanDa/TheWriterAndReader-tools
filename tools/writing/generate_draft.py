#!/usr/bin/env python3
"""Generate a chapter draft using local Ollama model."""
import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_context import (
    _first_existing,
    assert_write_inside_story_root,
    read_text_if_exists,
    resolve_story_root,
)
from scripts.ollama_client import call_ollama, select_ollama_model
from scripts.review import load_yaml


def load_brief(story_id: str, chapter_number: int) -> str:
    story_root = resolve_story_root(story_id, REPO_ROOT)
    brief_path = story_root / 'summaries' / f'chapter_{chapter_number:03d}_brief.md'
    if brief_path.exists():
        return brief_path.read_text(encoding='utf-8')
    return ''


def load_previous_summary(story_id: str, chapter_number: int) -> str:
    """Load summary of previous chapter if it exists."""
    if chapter_number <= 1:
        return ''
    prev_num = chapter_number - 1
    story_root = resolve_story_root(story_id, REPO_ROOT)
    # Try multiple summary locations
    for pattern in [
        story_root / 'summaries' / f'summary_chapter_{prev_num:03d}.md',
        story_root / 'summaries' / f'chapter_{prev_num:03d}_summary.md',
    ]:
        p = Path(pattern)
        if p.exists():
            return p.read_text(encoding='utf-8')
    return ''


def load_draft(story_id: str, chapter_number: int) -> str:
    story_root = resolve_story_root(story_id, REPO_ROOT)
    draft_path = story_root / 'drafts' / f'chapter_{chapter_number:03d}.md'
    if draft_path.exists():
        return draft_path.read_text(encoding='utf-8')
    return ''


def story_settings(config: dict) -> dict[str, str]:
    """Extract reusable story settings from supported config layouts."""
    story = config.get('story') if isinstance(config.get('story'), dict) else config
    if not isinstance(story, dict):
        story = {}
    return {
        'title': story.get('title') or 'Untitled Story',
        'language': story.get('language') or 'en',
    }


def build_generation_prompt(story_id: str, chapter_number: int) -> str:
    """Build the prompt for chapter generation."""
    story_root = resolve_story_root(story_id, REPO_ROOT)

    # Load story config
    config = load_yaml(_first_existing([story_root / 'story.yaml', story_root / 'story_config.yaml']))
    settings = story_settings(config)
    title = settings['title']
    language = settings['language']
    heading = chapter_heading(chapter_number, language)

    # Load brief
    brief = load_brief(story_id, chapter_number)

    # Load previous chapter summary
    prev_summary = load_previous_summary(story_id, chapter_number)

    # Load canon files
    canon_files = ['rules.md', 'characters.md', 'world.md', 'mystery_state.md', 'timeline.md']
    canon_text = ''
    for cf in canon_files:
        content = read_text_if_exists(story_root / 'canon' / cf)
        if content:
            canon_text += f'\n### {cf}\n{content}\n'

    # Load prior drafts for style reference (abbreviated)
    ch1 = load_draft(story_id, 1)
    ch2 = load_draft(story_id, 2)

    # Build prompt
    prompt = f"""You are drafting a reusable fiction chapter for "{title}".

Task: write chapter {chapter_number} in {language}.

## Style Reference

Use the opening of existing drafts only as a local style reference. Do not copy text.

### Prior Draft Sample A
{chr(10).join(ch1.split(chr(10))[:80])}

### Prior Draft Sample B
{chr(10).join(ch2.split(chr(10))[:60])}

## Story Reference

{canon_text}

## Chapter {chapter_number} Brief

{brief}

## Previous Chapter Summary

{prev_summary if prev_summary else "No previous chapter summary is available."}

## Draft Requirements

1. Write in the configured story language: {language}.
2. Use 3-5 scene sections unless the brief asks otherwise.
3. Use concrete scene action and dialogue instead of exposition dumps.
4. Follow Required Beats and Forbidden Spoilers from the brief.
5. Keep character knowledge limited to what the canon, brief, and prior summary allow.
6. End with a chapter-level hook when appropriate.
7. Do not include meta commentary, analysis, or author notes.
8. Output only the chapter text, starting with this heading:

{heading}"""

    return prompt


def chapter_number_to_chinese(n: int) -> str:
    """Convert chapter number to Chinese."""
    nums = {1: '一', 2: '二', 3: '三', 4: '四', 5: '五',
            6: '六', 7: '七', 8: '八', 9: '九', 10: '十'}
    return nums.get(n, str(n))


def chapter_heading(chapter_number: int, language: str) -> str:
    """Return a default chapter heading for the configured story language."""
    language_key = (language or 'en').lower()
    if language_key.startswith('zh') or language_key in {'chinese', 'mandarin'}:
        return f'# 第{chapter_number_to_chinese(chapter_number)}章'
    return f'# Chapter {chapter_number}'


def looks_like_chapter_heading(line: str) -> bool:
    """Detect common generated chapter headings."""
    stripped = line.strip()
    return bool(re.match(r'^#?\s*(Chapter\s+\d+|第.+章)\b', stripped, re.IGNORECASE))


def generate_chapter(
    story_id: str,
    chapter_number: int,
    model: str | None = None,
    interactive_model_select: bool = True,
) -> str:
    """Generate chapter via Ollama."""
    story_root = resolve_story_root(story_id, REPO_ROOT)
    config = load_yaml(_first_existing([story_root / 'story.yaml', story_root / 'story_config.yaml']))
    heading = chapter_heading(chapter_number, story_settings(config)['language'])
    prompt = build_generation_prompt(story_id, chapter_number)
    print(f'Prompt length: {len(prompt)} chars', flush=True)

    selected_model = select_ollama_model(
        'writer',
        repo_root=REPO_ROOT,
        requested_model=model,
        interactive=interactive_model_select,
    )
    print(f'Sending to Ollama ({selected_model or "unresolved model"})...', flush=True)
    chapter_text = call_ollama(
        prompt,
        role='writer',
        repo_root=REPO_ROOT,
        model=selected_model,
        interactive=False,
        temperature=0.7,
        num_predict=8192,
    ).strip()
    print(f'Generated {len(chapter_text)} chars', flush=True)
    if chapter_text.startswith('# Local Ollama Generation Failed'):
        return chapter_text

    # Clean up: remove any preamble before a recognizable chapter title.
    lines = chapter_text.split('\n')
    start_idx = 0
    for i, line in enumerate(lines):
        if looks_like_chapter_heading(line):
            start_idx = i
            break

    chapter_text = '\n'.join(lines[start_idx:]).strip()

    # Ensure chapter title format matches the configured story language.
    if not chapter_text.startswith(heading):
        chapter_lines = chapter_text.split('\n')
        for i, line in enumerate(chapter_lines[:5]):
            if looks_like_chapter_heading(line):
                chapter_lines[i] = heading
                chapter_text = '\n'.join(chapter_lines[i:]).strip()
                break
        else:
            chapter_text = f'{heading}\n\n{chapter_text}'

    return chapter_text


def main():
    parser = argparse.ArgumentParser(description='Generate a chapter draft using local Ollama.')
    parser.add_argument('story_id', nargs='?', help='Story id or story path.')
    parser.add_argument('chapter_number', nargs='?', type=int, help='Chapter number.')
    parser.add_argument('legacy_model', nargs='?', help='Optional model name for legacy positional usage.')
    parser.add_argument('--story', dest='story_option', help='Story id or story path.')
    parser.add_argument('--chapter', dest='chapter_option', type=int, help='Chapter number.')
    parser.add_argument('--model', help='Ollama model name.')
    parser.add_argument(
        '--no-model-select',
        action='store_true',
        help='Do not prompt for model selection; use routing defaults or --model.',
    )
    args = parser.parse_args()

    story_id = args.story_option or args.story_id
    chapter_number = args.chapter_option or args.chapter_number
    model = args.model or args.legacy_model
    if not story_id or chapter_number is None:
        parser.error('story and chapter are required')

    print(f'Generating chapter {chapter_number} for {story_id} using {model or "auto-select"}...', flush=True)

    chapter_text = generate_chapter(
        story_id,
        chapter_number,
        model,
        interactive_model_select=not args.no_model_select,
    )

    # Write to drafts
    story_root = resolve_story_root(story_id, REPO_ROOT)
    output_path = story_root / 'drafts' / f'chapter_{chapter_number:03d}.md'
    assert_write_inside_story_root(output_path.parent, story_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    assert_write_inside_story_root(output_path, story_root)
    output_path.write_text(chapter_text + '\n', encoding='utf-8')
    print(f'Written to {output_path} ({len(chapter_text)} chars)', flush=True)


if __name__ == '__main__':
    main()
