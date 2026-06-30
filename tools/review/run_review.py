#!/usr/bin/env python3
"""Run chapter reviewers through local Ollama using only the stdlib."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
from socket import timeout as SocketTimeout
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_context import assert_write_inside_story_root, resolve_story_root


MODEL = os.environ.get("LOCAL_REVIEW_MODEL", "gemma4:12b")
OLLAMA_URL = os.environ.get("LOCAL_REVIEW_OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_SHOW_URL = os.environ.get(
    "LOCAL_REVIEW_OLLAMA_SHOW_URL",
    OLLAMA_URL.split("/api/", 1)[0].rstrip("/") + "/api/show",
)
REQUEST_TIMEOUT = int(os.environ.get("LOCAL_REVIEW_TIMEOUT", "900"))
CONTEXT_PROBE_TIMEOUT = int(os.environ.get("LOCAL_REVIEW_CONTEXT_PROBE_TIMEOUT", "30"))
MAX_RESPONSE_CHARS = int(os.environ.get("LOCAL_REVIEW_MAX_CHARS", "1800"))
NUM_PREDICT = int(os.environ.get("LOCAL_REVIEW_NUM_PREDICT", "700"))
NUM_CTX = int(os.environ.get("LOCAL_REVIEW_NUM_CTX", "32768"))
CANON_CHARS = int(os.environ.get("LOCAL_REVIEW_CANON_CHARS", "6500"))
SECTION_SAMPLE_LINES = int(os.environ.get("LOCAL_REVIEW_SECTION_LINES", "8"))
RISK_LINE_LIMIT = int(os.environ.get("LOCAL_REVIEW_RISK_LINES", "25"))
MINIMAL_PROMPT = os.environ.get("LOCAL_REVIEW_MINIMAL", "") == "1"
ULTRA_MINIMAL_PROMPT = os.environ.get("LOCAL_REVIEW_ULTRA_MINIMAL", "") == "1"
STREAM_RESPONSE = os.environ.get("LOCAL_REVIEW_STREAM", "1") != "0"
REQUESTED_REVIEWERS = [
    name.strip()
    for name in os.environ.get("LOCAL_REVIEWERS", "").split(",")
    if name.strip()
]


REVIEWERS = {
    "continuity": "Check for conflicts with canon, timeline, identity rules, and character knowledge. Prioritize contradictions and uncertain points.",
    "character_arc": "Check whether character emotion, motivation, and behavior match the current story state.",
    "pacing": "Check chapter rhythm, scene transitions, information density, and whether the ending supports the chapter function.",
    "style": "Check readability, narrative voice consistency, repetition, over-explaining, awkward phrasing, or generated-text artifacts.",
    "mystery_fairness": "Check whether hidden facts, clues, or reveals are disclosed earlier than the brief or canon allows.",
    "movie_director": "Check visual clarity, staging, emotional beats, transitions, and concrete performable action.",
}


@contextmanager
def hard_timeout(seconds: int):
    """Bound slow local model streams; urllib's timeout only covers socket stalls."""
    def handle_timeout(_signum, _frame):
        raise TimeoutError(f"local reviewer exceeded {seconds}s")

    previous = signal.signal(signal.SIGALRM, handle_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def read(story_root: Path, path: str) -> str:
    return (story_root / path).read_text(encoding="utf-8")


def _clean_cli_output(output: str) -> str:
    text = output.replace("\r", "")
    lines = [line.rstrip() for line in text.splitlines()]
    filtered = [
        line for line in lines
        if line.strip() and "Thinking..." not in line and not line.lstrip().startswith("...")
    ]
    return "\n".join(filtered).strip()


def _extract_context_limit(value) -> int | None:
    candidates: list[int] = []

    def visit(item, key_hint: str = ""):
        if isinstance(item, dict):
            for key, nested in item.items():
                hint = str(key).lower()
                if isinstance(nested, int) and (
                    "context" in hint or "num_ctx" in hint or hint.endswith("ctx")
                ):
                    candidates.append(nested)
                visit(nested, hint)
            return
        if isinstance(item, list):
            for nested in item:
                visit(nested, key_hint)
            return
        if isinstance(item, str):
            for pattern in (
                r"(?:context length|context window|num_ctx|ctx)[^\d]{0,16}(\d{4,7})",
                r"(\d{4,7})[^\n]{0,24}(?:tokens?|context)",
            ):
                for match in re.finditer(pattern, item, flags=re.IGNORECASE):
                    candidates.append(int(match.group(1)))

    visit(value)
    plausible = [candidate for candidate in candidates if 1024 <= candidate <= 2_000_000]
    return max(plausible) if plausible else None


def inspect_context_limit() -> int | None:
    payload = json.dumps({"model": MODEL}).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_SHOW_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=CONTEXT_PROBE_TIMEOUT) as response:
            detected = _extract_context_limit(json.loads(response.read().decode("utf-8")))
            if detected:
                return detected
    except (OSError, URLError, json.JSONDecodeError):
        pass

    try:
        proc = subprocess.run(
            ["ollama", "show", MODEL, "--json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=CONTEXT_PROBE_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        return _extract_context_limit(json.loads(proc.stdout))
    except json.JSONDecodeError:
        return _extract_context_limit(proc.stdout)


def prepare_num_ctx(prompt: str) -> int:
    context_limit = inspect_context_limit()
    num_ctx = min(NUM_CTX, context_limit) if context_limit else NUM_CTX
    estimated_prompt_tokens = max(1, len(prompt) // 4)
    if estimated_prompt_tokens + NUM_PREDICT >= num_ctx:
        limit_note = f" detected model context limit={context_limit}" if context_limit else ""
        raise RuntimeError(
            "local review prompt is likely too large for the selected model "
            f"(estimated_prompt_tokens={estimated_prompt_tokens}, "
            f"num_predict={NUM_PREDICT}, num_ctx={num_ctx}.{limit_note})"
        )
    return num_ctx


def generate_via_cli(prompt: str) -> str:
    with hard_timeout(REQUEST_TIMEOUT):
        proc = subprocess.run(
            ["ollama", "run", MODEL],
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
            timeout=REQUEST_TIMEOUT,
        )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(f"ollama CLI failed ({proc.returncode}): {stderr or 'no stderr'}")
    text = _clean_cli_output(proc.stdout)
    if not text:
        raise RuntimeError("ollama CLI returned an empty response")
    return text


def generate(prompt: str) -> str:
    num_ctx = prepare_num_ctx(prompt)
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": STREAM_RESPONSE,
        "options": {
            "temperature": 0.25,
            "num_ctx": num_ctx,
            "num_predict": NUM_PREDICT,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        chunks = []
        started = time.monotonic()
        with hard_timeout(REQUEST_TIMEOUT):
            socket_timeout = REQUEST_TIMEOUT if not STREAM_RESPONSE else min(30, REQUEST_TIMEOUT)
            with urllib.request.urlopen(request, timeout=socket_timeout) as response:
                if not STREAM_RESPONSE:
                    event = json.loads(response.read().decode("utf-8"))
                    text = (event.get("response") or "").strip()
                    if text:
                        return text
                    diagnostics = [
                        f"{key}={event[key]}"
                        for key in ("done", "done_reason", "total_duration", "eval_count")
                        if key in event
                    ]
                    raise RuntimeError(
                        f"local model returned an empty response ({', '.join(diagnostics)})."
                    )
                for raw_line in response:
                    if time.monotonic() - started > REQUEST_TIMEOUT:
                        raise TimeoutError(f"local reviewer exceeded {REQUEST_TIMEOUT}s")
                    if not raw_line.strip():
                        continue
                    event = json.loads(raw_line.decode("utf-8"))
                    chunks.append(event.get("response", ""))
                    if event.get("done") or sum(len(chunk) for chunk in chunks) >= MAX_RESPONSE_CHARS:
                        break
        text = "".join(chunks).strip()
        if text:
            return text
        raise RuntimeError("local model returned an empty response (stream ended without text).")
    except RuntimeError as exc:
        if "empty response" not in str(exc):
            raise
        return generate_via_cli(prompt)


def make_draft_extract(draft: str) -> str:
    lines = draft.splitlines()
    section_starts = [index for index, line in enumerate(lines) if line.startswith("## ")]
    section_samples = []
    for start in section_starts:
        section_samples.append("\n".join(lines[start : start + SECTION_SAMPLE_LINES]))

    risk_terms = [
        "secret",
        "truth",
        "revealed",
        "forbidden",
        "prophecy",
        "memory",
        "identity",
        "timeline",
        "rule",
        "power",
        "betrayal",
        "真相",
        "秘密",
        "規則",
        "記憶",
        "secreto",
        "verdad",
    ]
    risk_lines = [
        f"{index + 1}: {line}"
        for index, line in enumerate(lines)
        if any(term in line for term in risk_terms)
    ]
    return (
        "[Chapter Samples]\n"
        + "\n\n".join(section_samples)
        + "\n\n[Lines Matching Generic Risk Terms]\n"
        + "\n".join(risk_lines[:RISK_LINE_LIMIT])
    )


def review_prompt(name: str, focus: str, canon: str, brief: str, draft_extract: str) -> str:
    if ULTRA_MINIMAL_PROMPT:
        return f"""Output only the review result. Do not include preamble, hidden reasoning, or blank lines.
Use exactly four lines:
# {name} Review
Verdict: pass|needs_revision|blocked
Issue: severity=none|minor|major|blocker; reason=one sentence; task=one sentence
Risk: one sentence

You are a local fiction reviewer. Do not rewrite the chapter and do not add canon. Judge only from the supplied materials. Mark uncertainty explicitly.
Review focus: {focus}

[BRIEF]
{brief[:900]}

[CANON EXCERPT]
{canon[:900]}

[DRAFT EXTRACT]
{draft_extract}
"""

    if MINIMAL_PROMPT:
        return f"""You are a local fiction reviewer. Do not rewrite the chapter and do not add canon. Judge only from the supplied materials. Mark uncertainty explicitly.

Reviewer: {name}
Focus: {focus}

Output in the story's configured language when clear from the materials; otherwise use English.
Keep the review under 220 words and use this format:
# {name} Review
## Verdict
## Issues
- severity: blocker|major|minor|none
  reasoning:
  task:
## Risks

[CANON]
{canon}

[BRIEF]
{brief}

[DRAFT EXTRACT]
{draft_extract}
"""

    return f"""You are a local fiction reviewer. Do not rewrite the chapter and do not add canon.
Judge only from the canon, brief, and draft extract below. Mark uncertainty explicitly.

Reviewer: {name}
Review focus: {focus}

Use this output format:
# {name} Review
## Summary
## Strengths
## Issues
- severity: ...
  reasoning: ...
  suggested revision task: ...
## Contradiction Risks
## Canon Risks
## Spoiler Risks
## Revision Tasks
## Optional Canon Update Proposals

Keep the review under 600 words and list only the highest risks. Limit Issues to three items.
You are seeing chapter samples and risk-term lines, not the full draft. If the full draft is needed to confirm something, mark it as uncertain.

[CANON]
{canon}

[CHAPTER BRIEF]
{brief}

[DRAFT EXTRACT]
{draft_extract}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local chapter reviewers for a story.")
    parser.add_argument("chapter_number", nargs="?", type=int, help="Chapter number.")
    parser.add_argument(
        "--story",
        default=os.environ.get("LOCAL_REVIEW_STORY"),
        help="Story id or path. Defaults to LOCAL_REVIEW_STORY.",
    )
    parser.add_argument("--chapter", dest="chapter_option", type=int, help="Chapter number.")
    args = parser.parse_args()
    args.chapter_number = args.chapter_option or args.chapter_number
    if not args.story:
        parser.error("--story is required unless LOCAL_REVIEW_STORY is set")
    if args.chapter_number is None:
        parser.error("chapter number is required")
    return args


def main() -> int:
    args = parse_args()
    chapter = args.chapter_number
    story_root = resolve_story_root(args.story, ROOT)
    canon_files = [
        "canon/world.md",
        "canon/rules.md",
        "canon/characters.md",
        "canon/mystery_state.md",
    ]
    canon = "\n\n".join(
        read(story_root, path) for path in canon_files if (story_root / path).exists()
    )
    canon = canon[:CANON_CHARS]
    brief = read(story_root, f"summaries/chapter_{chapter:03d}_brief.md")
    draft = read(story_root, f"drafts/chapter_{chapter:03d}.md")
    draft_extract = make_draft_extract(draft)
    out_dir = story_root / "reviews" / f"chapter_{chapter:03d}"
    assert_write_inside_story_root(out_dir, story_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    current_outputs = {}
    reviewers = REVIEWERS
    if REQUESTED_REVIEWERS:
        unknown = [name for name in REQUESTED_REVIEWERS if name not in REVIEWERS]
        if unknown:
            print(f"unknown reviewers: {', '.join(unknown)}", file=sys.stderr)
            return 2
        reviewers = {name: REVIEWERS[name] for name in REQUESTED_REVIEWERS}

    failed = False
    for name, focus in reviewers.items():
        print(f"running {name}", flush=True)
        try:
            output = generate(review_prompt(name, focus, canon, brief, draft_extract))
        except (TimeoutError, SocketTimeout, URLError, OSError, RuntimeError) as exc:
            output = f"# {name} Review\n\nERROR: local reviewer failed: {exc}"
            failed = True
        if not output:
            output = f"# {name} Review\n\nERROR: local model returned an empty response."
            failed = True
        out_path = out_dir / f"{name}.md"
        assert_write_inside_story_root(out_path, story_root)
        out_path.write_text(output + "\n", encoding="utf-8")
        current_outputs[name] = output

    combined_parts = []
    for name in REVIEWERS:
        if name in current_outputs:
            combined_parts.append(current_outputs[name])
            continue
        existing_path = out_dir / f"{name}.md"
        if existing_path.exists():
            combined_parts.append(existing_path.read_text(encoding="utf-8").strip())
    combined = "\n\n---\n\n".join(combined_parts) + "\n"
    combined_path = out_dir / "combined_review.md"
    assert_write_inside_story_root(combined_path, story_root)
    combined_path.write_text(combined, encoding="utf-8")
    print(f"wrote {combined_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
