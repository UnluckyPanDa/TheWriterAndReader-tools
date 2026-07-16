from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.review.rereview import rereview_explanation
from tools.review.run_review import run_review


FIXTURES = Path(__file__).parent / "fixtures"


class RereviewTests(unittest.TestCase):
    def copy_workspace(self, temp_dir: str) -> Path:
        target = Path(temp_dir) / "workspace"
        shutil.copytree(FIXTURES / "workspace_template", target)
        (target / "workspace.template.yaml").replace(target / "workspace.yaml")
        return target

    def test_writer_explanation_can_be_rereviewed_only_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = str(FIXTURES / "mock_config.yaml")
            run_review(workspace, "story-1", 1, config)

            outputs = rereview_explanation(
                workspace,
                "story-1",
                1,
                "editor",
                "The cited sentence reflects the visible action in the preceding paragraph.",
                config,
            )

            self.assertTrue(outputs["replacement_report"].exists())
            self.assertTrue(outputs["review_gate"].exists())
            explanation = story / "reviews" / "chapter" / "001" / "writer_explanations" / "standard.editor.md"
            self.assertTrue(explanation.exists())
            with self.assertRaisesRegex(RuntimeError, "already been used"):
                rereview_explanation(workspace, "story-1", 1, "editor", "A second explanation.", config)


if __name__ == "__main__":
    unittest.main()
