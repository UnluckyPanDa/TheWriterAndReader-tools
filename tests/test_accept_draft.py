from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.review.run_review import run_review
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


if __name__ == "__main__":
    unittest.main()
