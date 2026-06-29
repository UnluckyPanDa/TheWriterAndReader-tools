from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

from scripts.build_context import (
    REPO_ROOT,
    assert_write_inside_story_root,
    build_context_packet,
    resolve_story_root,
)
from scripts.doctor import main as doctor_main
from scripts.review import review_chapter


def init_story(story_id: str, repo_root: Path = REPO_ROOT) -> Path:
    source = repo_root / "templates" / "story"
    target = resolve_story_root(story_id, repo_root)
    if target.exists():
        raise FileExistsError(f"Story already exists: {target}")
    shutil.copytree(source, target)
    return target


def propose_canon_update(story_id: str, chapter_number: int, repo_root: Path = REPO_ROOT) -> Path:
    story = resolve_story_root(story_id, repo_root)
    proposal_dir = story / "canon_updates" / "pending"
    assert_write_inside_story_root(proposal_dir, story)
    proposal_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = proposal_dir / f"proposal_chapter_{chapter_number:03d}_{stamp}.md"
    assert_write_inside_story_root(path, story)
    path.write_text(
        f"""# Canon Update Proposal

Story: {story_id}
Chapter: {chapter_number}
Created: {stamp}

## Proposed Change

- Describe the canon change here.

## Evidence

- Reference chapter lines, review reports, or user notes.

## Target Canon File

- `canon/world.md`, `canon/rules.md`, `canon/timeline.md`, `canon/characters.md`, or `canon/mystery_state.md`

## Risk

- Note continuity, spoiler, or future-plot risks before accepting.
""",
        encoding="utf-8",
    )
    return path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def accept_canon_update(story_id: str, proposal_file: str, repo_root: Path = REPO_ROOT) -> Path:
    story = resolve_story_root(story_id, repo_root)
    pending_root = (story / "canon_updates" / "pending").resolve(strict=False)
    legacy_root = (story / "proposed_canon_updates").resolve(strict=False)
    proposal_path = Path(proposal_file)
    if proposal_path.is_absolute():
        proposal_path = proposal_path.resolve(strict=False)
    else:
        for root in [pending_root, legacy_root]:
            candidate = (root / proposal_file).resolve(strict=False)
            if candidate.exists():
                proposal_path = candidate
                break
        else:
            proposal_path = (pending_root / proposal_file).resolve(strict=False)
    if not any(_is_relative_to(proposal_path, root) for root in [pending_root, legacy_root]):
        raise ValueError("Proposal must live under the story canon update proposal directories.")
    if not proposal_path.exists():
        raise FileNotFoundError(proposal_path)

    changelog = story / "canon" / "CHANGELOG.md"
    assert_write_inside_story_root(changelog, story)
    changelog.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    entry = f"\n## {stamp}\n\nAccepted proposal: `{proposal_path.name}`\n\nManual canon edit still required if the proposal changes canon text.\n"
    with changelog.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    return changelog


def main() -> int:
    parser = argparse.ArgumentParser(description="Local novel AI workbench.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor")

    init_parser = sub.add_parser("init-story")
    init_parser.add_argument("--story", required=True)

    context_parser = sub.add_parser("build-context")
    context_parser.add_argument("--story", required=True)
    context_parser.add_argument("--chapter", required=True, type=int)

    review_parser = sub.add_parser("review")
    review_parser.add_argument("--story", required=True)
    review_parser.add_argument("--chapter", required=True, type=int)
    review_parser.add_argument("--reviewers", default="")
    review_parser.add_argument("--model")
    review_parser.add_argument("--no-model-select", action="store_true")

    propose_parser = sub.add_parser("propose-canon-update")
    propose_parser.add_argument("--story", required=True)
    propose_parser.add_argument("--chapter", required=True, type=int)

    accept_parser = sub.add_parser("accept-canon-update")
    accept_parser.add_argument("--story", required=True)
    accept_parser.add_argument("--proposal", required=True)

    args = parser.parse_args()

    if args.command == "doctor":
        return doctor_main()
    if args.command == "init-story":
        print(init_story(args.story))
        return 0
    if args.command == "build-context":
        print(build_context_packet(args.story, args.chapter))
        return 0
    if args.command == "review":
        reviewers = [item.strip() for item in args.reviewers.split(",") if item.strip()] or None
        print(
            review_chapter(
                args.story,
                args.chapter,
                reviewers,
                model=args.model,
                interactive_model_select=not args.no_model_select,
            )
        )
        return 0
    if args.command == "propose-canon-update":
        print(propose_canon_update(args.story, args.chapter))
        return 0
    if args.command == "accept-canon-update":
        print(accept_canon_update(args.story, args.proposal))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
