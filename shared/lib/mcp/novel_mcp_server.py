#!/usr/bin/env python3
"""Optional local MCP server for the novel AI workbench.

The server keeps canon writes behind proposal files. It is intentionally thin:
the command-line scripts remain the source of truth for local behavior.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_context import build_context_packet, read_text_if_exists
from scripts.novel import init_story as init_story_command
from scripts.novel import propose_canon_update as propose_canon_update_command
from scripts.ollama_client import call_ollama
from scripts.review import review_chapter as review_chapter_command

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - exercised only when optional dep is absent
    FastMCP = None  # type: ignore[assignment]


def _story_dir(story_id: str) -> Path:
    return REPO_ROOT / "stories" / story_id


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return data


def list_stories() -> list[str]:
    """Return story IDs available under stories/."""
    stories_dir = REPO_ROOT / "stories"
    if not stories_dir.exists():
        return []
    return sorted(path.name for path in stories_dir.iterdir() if path.is_dir())


def init_story(story_id: str) -> str:
    """Create a story from templates/story."""
    target = init_story_command(story_id)
    return str(target.relative_to(REPO_ROOT))


def get_story_config(story_id: str) -> dict[str, Any]:
    """Load stories/<story_id>/story_config.yaml."""
    return _load_yaml(_story_dir(story_id) / "story_config.yaml")


def build_context(story_id: str, chapter_number: int) -> str:
    """Build and return a context packet path."""
    output = build_context_packet(story_id, chapter_number, repo_root=REPO_ROOT)
    return str(output.relative_to(REPO_ROOT))


def review_chapter(
    story_id: str,
    chapter_number: int,
    reviewers: str | list[str] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Run local reviewer prompts through Ollama and save reports."""
    reviewer_filter: list[str] | None
    if isinstance(reviewers, str):
        reviewer_filter = [item.strip() for item in reviewers.split(",") if item.strip()]
    else:
        reviewer_filter = reviewers
    results = review_chapter_command(
        story_id,
        chapter_number,
        reviewer_filter,
        repo_root=REPO_ROOT,
        model=model,
        interactive_model_select=False,
    )
    return {
        "combined": str(results["combined"].relative_to(REPO_ROOT)),
        "context": str(results["context"].relative_to(REPO_ROOT)),
        "reports": {
            reviewer_id: str(path.relative_to(REPO_ROOT))
            for reviewer_id, path in results["reports"].items()
        },
    }


def write_chapter_draft(
    story_id: str,
    chapter_number: int,
    brief_file: str | None = None,
    model: str | None = None,
) -> str:
    """Write a local draft with the writer model without touching canon."""
    story_path = _story_dir(story_id)
    if not story_path.exists():
        raise FileNotFoundError(f"Story not found: {story_id}")

    context_path = build_context_packet(story_id, chapter_number, repo_root=REPO_ROOT)
    context_text = context_path.read_text(encoding="utf-8")
    extra_brief = ""
    if brief_file:
        brief_path = story_path / brief_file
        if not brief_path.exists():
            raise FileNotFoundError(f"Brief file not found: {brief_path}")
        extra_brief = "\n\n# Extra Brief\n" + brief_path.read_text(encoding="utf-8")

    prompt = f"""你是本機長篇小說寫作模型。請只根據下列章節脈絡撰寫草稿。

規則：
- 不要修改或新增 canon 檔案。
- 不要提前揭露 Forbidden Spoilers。
- 若 canon 不足，請在草稿末尾列出需要作者決定的問題。
- 請輸出章節草稿，不要輸出評論。

{context_text}{extra_brief}
"""
    draft = call_ollama(
        prompt,
        role="writer",
        repo_root=REPO_ROOT,
        model=model,
        interactive=False,
    )
    drafts_dir = story_path / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    target = drafts_dir / f"chapter_{chapter_number:03d}.md"
    if target.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = drafts_dir / f"chapter_{chapter_number:03d}_{stamp}.md"
    target.write_text(draft, encoding="utf-8")
    return str(target.relative_to(REPO_ROOT))


def propose_canon_update(story_id: str, chapter_number: int) -> str:
    """Create a proposal file under proposed_canon_updates."""
    proposal = propose_canon_update_command(story_id, chapter_number)
    return str(proposal.relative_to(REPO_ROOT))


def list_reviewer_profiles(story_id: str) -> list[str]:
    """List story-local reviewer profile markdown files."""
    profiles_dir = _story_dir(story_id) / "reviewer_profiles"
    if not profiles_dir.exists():
        return []
    return sorted(path.name for path in profiles_dir.glob("*.md"))


def add_reviewer_profile(story_id: str, reviewer_id: str, profile_text: str) -> str:
    """Add a story-local reviewer profile without modifying global defaults."""
    profiles_dir = _story_dir(story_id) / "reviewer_profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    safe_id = reviewer_id.replace("/", "_").replace("\\", "_")
    target = profiles_dir / f"{safe_id}.md"
    if target.exists():
        raise FileExistsError(f"Reviewer profile already exists: {target}")
    target.write_text(profile_text, encoding="utf-8")
    return str(target.relative_to(REPO_ROOT))


if FastMCP is not None:
    mcp = FastMCP("novel-ai-workbench")
    mcp.tool()(list_stories)
    mcp.tool()(init_story)
    mcp.tool()(get_story_config)
    mcp.tool()(build_context)
    mcp.tool()(review_chapter)
    mcp.tool()(write_chapter_draft)
    mcp.tool()(propose_canon_update)
    mcp.tool()(list_reviewer_profiles)
    mcp.tool()(add_reviewer_profile)
else:
    mcp = None


def main() -> int:
    if mcp is None:
        print("Optional MCP dependency is not installed.")
        print("Install it in the local venv if needed, for example: pip install mcp")
        print("The CLI scripts work without MCP.")
        return 1
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
