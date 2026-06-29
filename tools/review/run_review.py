#!/usr/bin/env python3
"""Run chapter reviewers through local Ollama using only the stdlib."""

from __future__ import annotations

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


STORY_ROOT = resolve_story_root("story-1", ROOT)
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
    "continuity": "檢查章節是否違反既有 canon、時間線、身份規則、角色已知資訊。優先指出矛盾與不確定處。",
    "character_arc": "檢查湊/澪/詩織/孩子/同學的情緒與行為是否符合目前章節可知狀態，尤其湊與澪的思考差異。",
    "pacing": "檢查章節節奏、場景轉換、資訊密度、結尾鉤子是否支撐第一章功能。",
    "style": "檢查商業小說可讀性、敘事語氣、重複、抽象說明過多、語句不順或生成痕跡。",
    "mystery_fairness": "檢查是否過早透露鏡庭、十六年前、真希真相、九條能力、世界修補機制等未到章節的謎底。",
    "movie_director": "以電影導演角度檢查視覺清晰度、場面調度、情緒節拍、轉場、演員可表演的具體動作。",
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


def read(path: str) -> str:
    return (STORY_ROOT / path).read_text(encoding="utf-8")


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
        "修補",
        "世界的規則",
        "保護",
        "九條",
        "真希",
        "鏡",
        "十六",
        "疾病",
        "神經",
        "詩織",
        "心春",
        "悠",
        "數學",
        "作業",
    ]
    risk_lines = [
        f"{index + 1}: {line}"
        for index, line in enumerate(lines)
        if any(term in line for term in risk_terms)
    ]
    return (
        "[章節抽樣]\n"
        + "\n\n".join(section_samples)
        + "\n\n[需審查的風險句]\n"
        + "\n".join(risk_lines[:RISK_LINE_LIMIT])
    )


def review_prompt(name: str, focus: str, canon: str, brief: str, draft_extract: str) -> str:
    if ULTRA_MINIMAL_PROMPT:
        return f"""只輸出審稿結論，不要前言，不要思考過程，不要空白。
格式固定為四行：
# {name} Review
Verdict: pass|needs_revision|blocked
Issue: severity=none|minor|major|blocker; reason=一句話; task=一句話
Risk: 一句話

你是本地小說 reviewer。不可改寫章節，不可新增 canon；只根據材料判斷，不確定就寫「不確定」。
審閱重點: {focus}

[BRIEF]
{brief[:900]}

[CANON EXCERPT]
{canon[:900]}

[DRAFT EXTRACT]
{draft_extract}
"""

    if MINIMAL_PROMPT:
        return f"""本地小說 reviewer。不可改寫章節，不可新增 canon；只根據材料判斷，不確定就寫「不確定」。

Reviewer: {name}
重點: {focus}

輸出繁體中文，最多 220 字，格式：
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

    return f"""你是本地小說 reviewer，不可改寫章節，不可新增 canon。
請用繁體中文審閱第一章草稿。只根據下列 canon/brief/草稿判斷；不確定就標記不確定。

Reviewer: {name}
審閱重點: {focus}

必要輸出格式：
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

請控制在 600 字以內，只列最高風險；每個 Issues 最多 3 條。
你看到的是章節抽樣與風險句，不是全文；若需要全文才能確認，請標記「不確定」。

[CANON]
{canon}

[CHAPTER BRIEF]
{brief}

[DRAFT EXTRACT]
{draft_extract}
"""


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: local_chapter_review.py <chapter_number>", file=sys.stderr)
        return 2
    chapter = int(sys.argv[1])
    canon = "\n\n".join(
        [
            read("canon/world.md"),
            read("canon/rules.md"),
            read("canon/characters.md"),
            read("canon/mystery_state.md"),
        ]
    )
    canon = canon[:CANON_CHARS]
    brief = read(f"summaries/chapter_{chapter:03d}_brief.md")
    draft = read(f"drafts/chapter_{chapter:03d}.md")
    draft_extract = make_draft_extract(draft)
    out_dir = STORY_ROOT / "reviews" / f"chapter_{chapter}"
    assert_write_inside_story_root(out_dir, STORY_ROOT)
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
        assert_write_inside_story_root(out_path, STORY_ROOT)
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
    assert_write_inside_story_root(combined_path, STORY_ROOT)
    combined_path.write_text(combined, encoding="utf-8")
    print(f"wrote {combined_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
