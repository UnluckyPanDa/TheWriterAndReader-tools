#!/usr/bin/env python3
"""Generate a chapter draft using local Ollama model."""
import argparse
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


def build_generation_prompt(story_id: str, chapter_number: int) -> str:
    """Build the prompt for chapter generation."""
    story_root = resolve_story_root(story_id, REPO_ROOT)

    # Load story config
    config = load_yaml(_first_existing([story_root / 'story.yaml', story_root / 'story_config.yaml']))
    title = config.get('title', '港與航道')

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

    # Load existing chapter 1-2 for style reference (abbreviated)
    ch1 = load_draft(story_id, 1)
    ch2 = load_draft(story_id, 2)

    # Build prompt
    prompt = f"""你是一位繁體中文文學小說作家。你的任務是為長篇小說《{title}》撰寫第 {chapter_number} 章的完整草稿。

## 風格參考

以下是前兩章的開頭，供你參考文風和敘事語氣：

### 第一章開頭（約前80行）
{chr(10).join(ch1.split(chr(10))[:80])}

### 第二章開頭（約前60行）
{chr(10).join(ch2.split(chr(10))[:60])}

## 故事規範（Canon）

{canon_text}

## 第 {chapter_number} 章大綱（Brief）

{brief}

## 前一章摘要

{prev_summary if prev_summary else '（這是第一部早期章節，請根據已有章節脈絡繼續。）'}

## 寫作要求

1. 使用繁體中文（zh-Hant）書寫。
2. 章節長度約 150-250 行，分為 3-5 個場景節。
3. 每個場景節用 `## 第X節：標題` 格式。
4. 保持與前兩章一致的文學小說風格：細膩的心理描寫、具體的場景感、情感張力。
5. 嚴格遵守 Brief 中的 Required Beats 和 Forbidden Spoilers。
6. 湊的思維方式：問題→分析→判斷→決定。澪的思維方式：感受→情緒→理解→判斷。
7. 不要使用設定說明（info dump），用場景和對話自然展現。
8. 章末要有 ending hook，讓讀者想繼續讀下一章。
9. 不要加入任何元評論或作者註解，只輸出小說正文。

現在請寫出第 {chapter_number} 章的完整草稿。直接從章節標題開始：

# 第{chapter_number_to_chinese(chapter_number)}章"""

    return prompt


def chapter_number_to_chinese(n: int) -> str:
    """Convert chapter number to Chinese."""
    nums = {1: '一', 2: '二', 3: '三', 4: '四', 5: '五',
            6: '六', 7: '七', 8: '八', 9: '九', 10: '十'}
    return nums.get(n, str(n))


def generate_chapter(
    story_id: str,
    chapter_number: int,
    model: str | None = None,
    interactive_model_select: bool = True,
) -> str:
    """Generate chapter via Ollama."""
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

    # Clean up: remove any preamble before the chapter title
    lines = chapter_text.split('\n')
    start_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('# 第') or line.startswith('第') and '章' in line[:10]:
            start_idx = i
            break

    chapter_text = '\n'.join(lines[start_idx:])

    # Ensure chapter title format
    ch_cn = chapter_number_to_chinese(chapter_number)
    if not chapter_text.startswith(f'# 第{ch_cn}章'):
        # Try to find title in first few lines
        for i, line in enumerate(lines[:5]):
            if ch_cn in line and '章' in line:
                chapter_text = '\n'.join(lines[i:])
                break
        else:
            chapter_text = f'# 第{ch_cn}章\n\n{chapter_text}'

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
