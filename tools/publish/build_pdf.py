from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_context import assert_write_inside_story_root, resolve_story_root


STORY_ROOT = resolve_story_root("story-1", ROOT)
DRAFTS_DIR = STORY_ROOT / "drafts"
PUBLISH_DIR = STORY_ROOT / "build" / "publish"
SOURCE_PATH = PUBLISH_DIR / "part_1_publish_source.txt"
PDF_PATH = PUBLISH_DIR / "part_1_publish.pdf"

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


def normalize_chapter_heading(raw_heading: str) -> str:
    heading = raw_heading.strip()
    chapter_match = re.match(r"Chapter\s+(\d+)\s*[　 ]*(.+)", heading)
    if chapter_match:
        number = int(chapter_match.group(1))
        title = chapter_match.group(2).strip()
        chapter_label = CHINESE_NUMERALS.get(number, str(number))
        return f"第{chapter_label}章　{title}"
    return heading


def clean_line(line: str) -> str:
    stripped = line.rstrip("\n")
    if stripped.startswith("# "):
        return normalize_chapter_heading(stripped[2:])
    if stripped.startswith("## "):
        return stripped[3:].strip()
    if stripped.strip() == "---":
        return ""
    return stripped.replace("`", "")


def build_source_text() -> str:
    chapter_paths = sorted(DRAFTS_DIR.glob("chapter_0*.md"))
    blocks: list[str] = ["港與航道", "", "第一部", ""]

    for index, chapter_path in enumerate(chapter_paths, start=1):
        lines = chapter_path.read_text(encoding="utf-8").splitlines()
        cleaned_lines = [clean_line(line) for line in lines]
        chapter_text = "\n".join(cleaned_lines).strip()
        if not chapter_text:
            continue
        if index > 1:
            blocks.extend(["", "\f", ""])
        blocks.append(chapter_text)

    return "\n".join(blocks).rstrip() + "\n"


def render_pdf(source_path: Path, pdf_path: Path) -> None:
    assert_write_inside_story_root(pdf_path, STORY_ROOT)
    with pdf_path.open("wb") as pdf_file:
        subprocess.run(
            ["cupsfilter", "-m", "application/pdf", str(source_path)],
            check=True,
            stdout=pdf_file,
        )


def main() -> None:
    assert_write_inside_story_root(PUBLISH_DIR, STORY_ROOT)
    assert_write_inside_story_root(SOURCE_PATH, STORY_ROOT)
    assert_write_inside_story_root(PDF_PATH, STORY_ROOT)
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
    source_text = build_source_text()
    SOURCE_PATH.write_text(source_text, encoding="utf-8")
    render_pdf(SOURCE_PATH, PDF_PATH)
    print(f"Wrote {SOURCE_PATH}")
    print(f"Wrote {PDF_PATH}")


if __name__ == "__main__":
    main()
