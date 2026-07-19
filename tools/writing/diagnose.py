"""Deterministic prose diagnostics for chapter drafts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from statistics import mean
from typing import Any, Iterable

from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.safe_write import safe_write_file
from shared.lib.story_loader import load_story_yaml
from shared.lib.workspace_loader import resolve_story_path


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:['’-][A-Za-z0-9_]+)*|[\u3400-\u9fff]")
DIALOGUE_RE = re.compile(r'(^|\n)\s*(?:[“「『\"]|[-—]\s)')
EMOTION_TERMS = {
    "afraid",
    "angry",
    "anxious",
    "embarrassed",
    "happy",
    "sad",
    "uneasy",
    "worried",
    "害怕",
    "憤怒",
    "焦慮",
    "尷尬",
    "高興",
    "悲傷",
    "不安",
    "擔心",
}
SOURCE_GROUPS = (
    ("canon", "canon", "*.md"),
    ("planning", "storyline", "*.md"),
    ("summary", "summaries", "*.md"),
    ("review", "reviews", "*.md"),
    ("writer_profile", "writer", "*.md"),
)


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def _paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]


def _source_files(story_path: Path, chapter: int) -> list[tuple[str, Path]]:
    sources: list[tuple[str, Path]] = []
    for category, relative, pattern in SOURCE_GROUPS:
        root = story_path / relative
        if root.exists():
            for path in sorted(root.rglob(pattern)):
                if not path.is_file():
                    continue
                if category == "review" and path.parent == root / "chapter" / f"{chapter:03d}":
                    continue
                sources.append((category, path))
    chapter_root = story_path / "chapters"
    for path in sorted(chapter_root.glob("chapter_*.md")):
        match = re.search(r"chapter_(\d+)\.md$", path.name)
        if match and int(match.group(1)) < chapter:
            sources.append(("previous_chapter", path))
    return sources


def _ngram_locations(tokens: list[str], size: int) -> dict[tuple[str, ...], list[int]]:
    locations: dict[tuple[str, ...], list[int]] = {}
    for index in range(len(tokens) - size + 1):
        locations.setdefault(tuple(tokens[index : index + size]), []).append(index)
    return locations


def _source_similarity_flags(
    draft_tokens: list[str],
    sources: Iterable[tuple[str, Path]],
    minimum_words: int,
    story_path: Path,
    exempt_tokens: set[str],
) -> list[dict[str, Any]]:
    draft_ngrams = _ngram_locations(draft_tokens, minimum_words)
    flags: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for category, path in sources:
        source_tokens = _tokens(path.read_text(encoding="utf-8"))
        for phrase in _ngram_locations(source_tokens, minimum_words):
            if exempt_tokens and set(phrase).issubset(exempt_tokens):
                continue
            if phrase not in draft_ngrams:
                continue
            phrase_text = " ".join(phrase)
            key = (str(path), phrase_text)
            if key in seen:
                continue
            seen.add(key)
            flags.append(
                {
                    "category": category,
                    "source": str(path.relative_to(story_path)),
                    "phrase": phrase_text,
                    "minimum_words": minimum_words,
                    "draft_token_index": draft_ngrams[phrase][0],
                }
            )
            if len(flags) >= 100:
                return flags
    return flags


def _semantic_repetition(paragraphs: list[str], threshold: float = 0.72) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for index in range(len(paragraphs) - 1):
        left = set(_tokens(paragraphs[index]))
        right = set(_tokens(paragraphs[index + 1]))
        if min(len(left), len(right)) < 8:
            continue
        similarity = len(left & right) / len(left | right)
        if similarity >= threshold:
            flags.append(
                {
                    "paragraphs": [index + 1, index + 2],
                    "similarity": round(similarity, 3),
                }
            )
    return flags


def _paragraph_function(paragraph: str) -> str:
    stripped = paragraph.lstrip()
    lowered = stripped.casefold()
    if DIALOGUE_RE.search(stripped):
        return "DIALOGUE"
    if re.search(r"\b(decided|chose|resolved|would|must)\b|決定|選擇|必須", lowered):
        return "DECISION"
    if re.search(r"\b(realized|learned|discovered|revealed|noticed)\b|發現|察覺|得知", lowered):
        return "REVELATION"
    if re.search(r"\b(because|therefore|so|consequence|result)\b|因此|所以|結果", lowered):
        return "CONSEQUENCE"
    if re.search(r"\b(then|later|after|before|meanwhile)\b|接著|之後|同時", lowered):
        return "TRANSITION"
    if re.search(r"\b(saw|heard|felt|smelled|watched|looked)\b|看見|聽見|感到|望著", lowered):
        return "OBSERVATION"
    if re.search(r"\b(said|asked|replied|whispered|shouted)\b|說|問|回答|低聲", lowered):
        return "REACTION"
    return "ACTION"


def _function_runs(functions: list[str], maximum: int = 3) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    start = 0
    while start < len(functions):
        end = start + 1
        while end < len(functions) and functions[end] == functions[start]:
            end += 1
        if end - start > maximum:
            flags.append({"function": functions[start], "paragraphs": [start + 1, end]})
        start = end
    return flags


def _repeated_openings(paragraphs: list[str]) -> list[dict[str, Any]]:
    openings: dict[tuple[str, ...], list[int]] = {}
    for index, paragraph in enumerate(paragraphs):
        opening = tuple(_tokens(paragraph)[:3])
        if len(opening) == 3:
            openings.setdefault(opening, []).append(index + 1)
    return [
        {"opening": " ".join(opening), "paragraphs": locations}
        for opening, locations in openings.items()
        if len(locations) > 1
    ]


def _repeated_phrases(tokens: list[str], size: int = 5) -> list[dict[str, Any]]:
    occurrences = _ngram_locations(tokens, size)
    return [
        {"phrase": " ".join(phrase), "token_indexes": indexes}
        for phrase, indexes in occurrences.items()
        if len(indexes) > 1
    ][:100]


def _review_issue_count(story_path: Path, chapter: int) -> int:
    review_root = story_path / "reviews" / "chapter" / f"{chapter:03d}"
    return sum(
        len(re.findall(r"(?m)^###\s+Issue\b", path.read_text(encoding="utf-8")))
        for path in review_root.glob("*.md")
        if path.name not in {"combined_review.md", "review_task_summary.md"}
    )


def _revision_cycle_count(story_path: Path, chapter: int) -> int:
    run_root = story_path / "runs" / f"chapter_{chapter:03d}"
    count = 0
    for path in run_root.glob("*/revision.json"):
        if path.is_file():
            count += 1
    return count


def _maximum_run(values: list[bool]) -> int:
    longest = current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def analyze_draft(
    story_path: str | Path,
    chapter: int,
    draft_text: str | None = None,
    semantic_threshold: float = 0.72,
    exact_min_words: int = 8,
    distinctive_min_words: int = 5,
) -> dict[str, Any]:
    """Return deterministic diagnostics without rewriting prose."""
    if not 0 <= semantic_threshold <= 1:
        raise ValueError("semantic_threshold must be between 0 and 1")
    if exact_min_words < 2 or distinctive_min_words < 2:
        raise ValueError("source phrase thresholds must be at least 2 words")
    root = Path(story_path).expanduser().resolve(strict=False)
    draft_path = root / "drafts" / f"chapter_{chapter:03d}.md"
    text = draft_text if draft_text is not None else draft_path.read_text(encoding="utf-8")
    paragraphs = _paragraphs(text)
    tokens = _tokens(text)
    functions = [_paragraph_function(paragraph) for paragraph in paragraphs]
    source_files = _source_files(root, chapter)
    story_yaml = load_story_yaml(root)
    diagnostic_config = story_yaml.get("writing_diagnostics", {})
    configured_exemptions = (
        diagnostic_config.get("source_similarity_exemptions", [])
        if isinstance(diagnostic_config, dict)
        else []
    )
    exemption_text = " ".join(
        [
            str(story_yaml.get("id", "")),
            str(story_yaml.get("title", "")),
            *(str(value) for value in configured_exemptions if isinstance(value, str)),
        ]
    )
    exempt_tokens = set(_tokens(exemption_text))
    exact_flags = _source_similarity_flags(tokens, source_files, exact_min_words, root, exempt_tokens)
    distinctive_flags = _source_similarity_flags(tokens, source_files, distinctive_min_words, root, exempt_tokens)
    word_counts = [len(_tokens(paragraph)) for paragraph in paragraphs]
    dialogue_paragraphs = sum(1 for paragraph in paragraphs if _paragraph_function(paragraph) == "DIALOGUE")
    exposition_flags = [
        function != "DIALOGUE" and len(_tokens(paragraph)) >= 40
        for function, paragraph in zip(functions, paragraphs)
    ]
    paragraphs_without_movement = sum(
        1
        for function, paragraph in zip(functions, paragraphs)
        if function == "OBSERVATION"
        and not re.search(r"\b(?:chose|decided|moved|took|gave|asked|answered|changed|left|entered)\b|決定|選擇|走|拿|給|問|回答|改變|離開|進入", paragraph, re.I)
    )
    emotion_count = sum(tokens.count(term.casefold()) for term in EMOTION_TERMS)
    repeated_phrases = _repeated_phrases(tokens)

    return {
        "schema_version": 1,
        "chapter": chapter,
        "draft": str(draft_path.relative_to(root)),
        "draft_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "metrics": {
            "word_count": len(tokens),
            "paragraph_count": len(paragraphs),
            "average_paragraph_words": round(mean(word_counts), 2) if word_counts else 0,
            "dialogue_percentage": round(dialogue_paragraphs * 100 / len(paragraphs), 2) if paragraphs else 0,
            "direct_emotion_label_count": emotion_count,
            "repeated_phrase_count": len(repeated_phrases),
            "exact_source_phrase_count": len(exact_flags),
            "distinctive_source_phrase_count": len(distinctive_flags),
            "semantic_repetition_count": len(_semantic_repetition(paragraphs, semantic_threshold)),
            "paragraphs_without_state_movement": paragraphs_without_movement,
            "exposition_concentration": _maximum_run(exposition_flags),
            "reviewer_issue_count": _review_issue_count(root, chapter),
            "rewrite_cycles_before_acceptance": _revision_cycle_count(root, chapter),
        },
        "paragraph_functions": [
            {"paragraph": index + 1, "function": function}
            for index, function in enumerate(functions)
        ],
        "flags": {
            "exact_source_phrases": exact_flags,
            "distinctive_source_phrases": distinctive_flags,
            "semantic_repetition": _semantic_repetition(paragraphs, semantic_threshold),
            "repeated_phrases": repeated_phrases,
            "repeated_openings": _repeated_openings(paragraphs),
            "paragraph_function_runs": _function_runs(functions),
        },
        "source_files_checked": [
            {"category": category, "path": str(path.relative_to(root))}
            for category, path in source_files
        ],
        "source_similarity_exemptions": sorted(exempt_tokens),
    }


def write_diagnostics(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    output_path: str | Path | None = None,
    semantic_threshold: float = 0.72,
    exact_min_words: int = 8,
    distinctive_min_words: int = 5,
) -> Path:
    """Analyze the active draft and persist its diagnostic report."""
    story_path = resolve_story_path(workspace_path, story_id)
    result = analyze_draft(
        story_path,
        chapter,
        semantic_threshold=semantic_threshold,
        exact_min_words=exact_min_words,
        distinctive_min_words=distinctive_min_words,
    )
    target = Path(output_path) if output_path else story_path / "context" / f"chapter_{chapter:03d}_writing_diagnostics.json"
    if not target.is_absolute():
        target = story_path / target
    assert_story_write_allowed(target, story_path)
    return safe_write_file(target, json.dumps(result, ensure_ascii=False, indent=2) + "\n", story_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose repetition, source reuse, and prose movement.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--story", required=True)
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--semantic-threshold", type=float, default=0.72)
    parser.add_argument("--exact-min-words", type=int, default=8)
    parser.add_argument("--distinctive-min-words", type=int, default=5)
    args = parser.parse_args(argv)
    print(
        write_diagnostics(
            args.workspace,
            args.story,
            args.chapter,
            semantic_threshold=args.semantic_threshold,
            exact_min_words=args.exact_min_words,
            distinctive_min_words=args.distinctive_min_words,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
