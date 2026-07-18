from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.review.run_review import rebuild_review_gate, run_review
from tools.writing.accept_draft import accept_draft


FIXTURES = Path(__file__).parent / "fixtures"


class AcceptDraftTests(unittest.TestCase):
    def copy_workspace(self, temp_dir: str) -> Path:
        target = Path(temp_dir) / "workspace"
        shutil.copytree(FIXTURES / "workspace_template", target)
        (target / "workspace.template.yaml").replace(target / "workspace.yaml")
        return target

    def test_accept_uses_reviewed_draft_for_chapter_summary_and_handover(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = str(FIXTURES / "mock_config.yaml")
            accepted = story / "chapters" / "chapter_001.md"
            accepted.unlink()
            draft = (story / "drafts" / "chapter_001.md").read_text(encoding="utf-8")
            run_review(workspace, "story-1", 1, config)

            outputs = accept_draft(workspace, "story-1", 1, config)

            self.assertEqual(outputs["accepted_chapter"].read_text(encoding="utf-8"), draft)
            self.assertTrue(outputs["accepted_summary"].read_text(encoding="utf-8").startswith("# Chapter 001 Accepted Summary"))
            self.assertTrue(outputs["handover"].read_text(encoding="utf-8").startswith("# Story Handover"))
            state = (story / "state" / "story_status.yaml").read_text(encoding="utf-8")
            self.assertIn("last_accepted_chapter: 1", state)
            provenance = json.loads((story / "runs" / "chapter_001_acceptance.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["source"], "drafts/chapter_001.md")

    def test_accept_rejects_draft_changed_after_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = str(FIXTURES / "mock_config.yaml")
            run_review(workspace, "story-1", 1, config)
            (story / "drafts" / "chapter_001.md").write_text("# Chapter 1\n\nChanged.\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "changed after"):
                accept_draft(workspace, "story-1", 1, config)

    def test_failed_grounding_repair_writes_no_acceptance_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = str(FIXTURES / "mock_config.yaml")
            run_review(workspace, "story-1", 1, config)
            watched = [
                story / "chapters" / "chapter_001.md",
                story / "summaries" / "summary_chapter_001.md",
                story / "context" / "handover.md",
                story / "state" / "chapter_status.yaml",
                story / "state" / "story_status.yaml",
            ]
            before = {path: path.read_bytes() if path.exists() else None for path in watched}
            continuity = {
                "schema_version": 1,
                "story_id": "story-1",
                "chapter": 1,
                "summary": {key: [] for key in ("events", "decisions", "discoveries", "relationship_changes", "practical_state", "unresolved_pressure")},
                "handover": {key: [] for key in ("ending_situation", "character_intentions", "relationship_state", "open_pressure", "reader_questions", "continuity_details")},
            }
            ungrounded = {
                "schema_version": 1,
                "story_id": "story-1",
                "chapter": 1,
                "grounded": False,
                "unsupported_claims": ["unsupported"],
                "name_conflicts": [],
                "thinking_trace_detected": False,
            }
            with patch(
                "tools.writing.accept_draft.attempt_structured_model_chain",
                side_effect=[
                    {"ok": True, "value": continuity, "attempts": []},
                    {"ok": True, "value": ungrounded, "attempts": []},
                    {"ok": True, "value": continuity, "attempts": []},
                    {"ok": True, "value": ungrounded, "attempts": []},
                ],
            ):
                with self.assertRaisesRegex(RuntimeError, "remained ungrounded"):
                    accept_draft(workspace, "story-1", 1, config)

            self.assertEqual(
                {path: path.read_bytes() if path.exists() else None for path in watched},
                before,
            )
            self.assertFalse((story / "runs" / "chapter_001_acceptance.json").exists())

    def test_failed_reviewer_preserves_current_records_but_blocks_stale_gate_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = str(FIXTURES / "mock_config.yaml")
            run_review(workspace, "story-1", 1, config)
            current = story / "reviews" / "chapter" / "001"
            before = {
                path.name: path.read_bytes()
                for path in current.iterdir()
                if path.is_file() and path.name.startswith(("standard.", "series.", "special."))
            }

            with patch(
                "tools.review.run_review.attempt_structured_model_chain",
                return_value={"ok": False, "attempts": [{"status": "invalid"}]},
            ):
                with self.assertRaisesRegex(RuntimeError, "failed for all configured models"):
                    run_review(workspace, "story-1", 1, config)

            self.assertEqual(
                {
                    path.name: path.read_bytes()
                    for path in current.iterdir()
                    if path.is_file() and path.name.startswith(("standard.", "series.", "special."))
                },
                before,
            )
            with self.assertRaisesRegex(RuntimeError, "no valid current reviewer reports"):
                rebuild_review_gate(workspace, "story-1", 1)


if __name__ == "__main__":
    unittest.main()
