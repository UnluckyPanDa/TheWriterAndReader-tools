from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_context import _first_existing, assert_write_inside_story_root, resolve_story_root
from scripts.review import load_yaml


DEFAULT_SOURCE_NAME = "publish_source.txt"
DEFAULT_PDF_NAME = "publish.pdf"

CHINESE_NUMERALS = {
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


def story_metadata(story_root: Path) -> dict[str, str]:
    config = load_yaml(_first_existing([story_root / "story.yaml", story_root / "story_config.yaml"]))
    story = config.get("story") if isinstance(config.get("story"), dict) else config
    if not isinstance(story, dict):
        story = {}
    return {
        "title": story.get("title") or "Untitled Story",
        "language": story.get("language") or "en",
    }


def is_chinese_language(language: str) -> bool:
    normalized = language.lower()
    return normalized.startswith("zh") or normalized in {"chinese", "mandarin"}


def normalize_chapter_heading(raw_heading: str, language: str) -> str:
    heading = raw_heading.strip()
    chapter_match = re.match(r"Chapter\s+(\d+)\s*[　 ]*(.+)", heading)
    if chapter_match and is_chinese_language(language):
        number = int(chapter_match.group(1))
        title = chapter_match.group(2).strip()
        chapter_label = CHINESE_NUMERALS.get(number, str(number))
        return f"第{chapter_label}章　{title}"
    return heading


def clean_line(line: str, language: str) -> str:
    stripped = line.rstrip("\n")
    if stripped.startswith("# "):
        return normalize_chapter_heading(stripped[2:], language)
    if stripped.startswith("## "):
        return stripped[3:].strip()
    if stripped.strip() == "---":
        return ""
    return stripped.replace("`", "")


def build_source_text(story_root: Path, title: str, part_title: str, language: str) -> str:
    chapter_paths = sorted((story_root / "drafts").glob("chapter_0*.md"))
    blocks: list[str] = [title, ""]
    if part_title:
        blocks.extend([part_title, ""])

    for index, chapter_path in enumerate(chapter_paths, start=1):
        lines = chapter_path.read_text(encoding="utf-8").splitlines()
        cleaned_lines = [clean_line(line, language) for line in lines]
        chapter_text = "\n".join(cleaned_lines).strip()
        if not chapter_text:
            continue
        if index > 1:
            blocks.extend(["", "\f", ""])
        blocks.append(chapter_text)

    return "\n".join(blocks).rstrip() + "\n"


def render_pdf(source_path: Path, pdf_path: Path, story_root: Path) -> None:
    assert_write_inside_story_root(pdf_path, story_root)
    with pdf_path.open("wb") as pdf_file:
        subprocess.run(
            ["cupsfilter", "-m", "application/pdf", str(source_path)],
            check=True,
            stdout=pdf_file,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a PDF from story draft chapters.")
    parser.add_argument("--story", required=True, help="Story id or path.")
    parser.add_argument("--title", help="Override publish title.")
    parser.add_argument("--part-title", default="", help="Optional part title.")
    parser.add_argument("--source-name", default=DEFAULT_SOURCE_NAME, help="Publish source filename.")
    parser.add_argument("--pdf-name", default=DEFAULT_PDF_NAME, help="PDF filename.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    story_root = resolve_story_root(args.story, ROOT)
    metadata = story_metadata(story_root)
    title = args.title or metadata["title"]
    language = metadata["language"]
    publish_dir = story_root / "build" / "publish"
    source_path = publish_dir / args.source_name
    pdf_path = publish_dir / args.pdf_name

    assert_write_inside_story_root(publish_dir, story_root)
    assert_write_inside_story_root(source_path, story_root)
    assert_write_inside_story_root(pdf_path, story_root)
    publish_dir.mkdir(parents=True, exist_ok=True)

    source_text = build_source_text(story_root, title, args.part_title, language)
    source_path.write_text(source_text, encoding="utf-8")
    render_pdf(source_path, pdf_path, story_root)
    print(f"Wrote {source_path}")
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
