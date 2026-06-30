"""Context packing and Markdown utility functions."""
from __future__ import annotations

import re
from pathlib import Path

from shared.lib.safe_write import safe_write_file


def count_words(text: str) -> int:
    """Count word-like tokens in text."""
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def estimate_tokens(text: str) -> int:
    """Estimate token count from words for budgeting context packs."""
    return max(1, int(count_words(text) * 1.35)) if text.strip() else 0


def trim_context_to_word_limit(text: str, max_words: int) -> str:
    """Trim text to a maximum number of words without raising on short text."""
    if max_words < 1:
        raise ValueError("max_words must be positive")
    words = re.findall(r"\S+", text)
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "\n\n[Trimmed to fit context budget.]"


def extract_section(markdown: str, heading: str) -> str:
    """Extract a Markdown section by exact heading text."""
    pattern = re.compile(rf"(^#+\s+{re.escape(heading)}\s*$)(.*?)(?=^#+\s+|\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(markdown)
    return match.group(2).strip() if match else ""


def replace_section(markdown: str, heading: str, content: str) -> str:
    """Replace or append a Markdown section with the given content."""
    section = f"## {heading}\n{content.strip()}\n"
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$.*?(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL)
    if pattern.search(markdown):
        return pattern.sub(section, markdown).rstrip() + "\n"
    return markdown.rstrip() + "\n\n" + section


def render_template(template: str, values: dict) -> str:
    """Render a small {{name}} template with explicit string replacement."""
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + str(key) + "}}", str(value))
    missing = sorted(set(re.findall(r"{{\s*([a-zA-Z0-9_]+)\s*}}", rendered)))
    if missing:
        raise ValueError(f"Missing template values for: {', '.join(missing)}")
    return rendered


def load_markdown(path: str | Path, default: str = "") -> str:
    """Load Markdown text, returning default when the file is absent."""
    markdown_path = Path(path)
    if not markdown_path.exists():
        return default
    return markdown_path.read_text(encoding="utf-8")


def write_markdown(path: str | Path, content: str, allowed_root: str | Path) -> Path:
    """Write Markdown text using safe root checks."""
    if not content.strip():
        raise ValueError(f"Refusing to write empty Markdown file: {path}")
    return safe_write_file(path, content, allowed_root)
