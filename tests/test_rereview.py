from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.review.rereview import (
    _assert_new_rereview_thread,
    _higher_intelligence_chain,
    _require_higher_result_intelligence,
    _rereview_intelligence,
    rereview_explanation,
)
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
            reviewer_config = story / "reviewers" / "reviewer_config.yaml"
            original_reviewer_config = reviewer_config.read_text(encoding="utf-8")
            changed_reviewer_config = original_reviewer_config.replace(
                "  editor:\n    enabled: true\n    can_block_gate: true\n"
                "    provider_group: mock_first\n    intelligence: medium",
                "  editor:\n    enabled: true\n    can_block_gate: true\n"
                "    provider_group: mock_first\n    intelligence: low",
            )
            self.assertNotEqual(changed_reviewer_config, original_reviewer_config)
            reviewer_config.write_text(
                changed_reviewer_config,
                encoding="utf-8",
            )

            outputs = rereview_explanation(
                workspace,
                "story-1",
                1,
                "editor",
                "The cited sentence reflects the visible action in the preceding paragraph.",
                config,
            )

            self.assertTrue(outputs["replacement_report"].exists())
            self.assertTrue(outputs["replacement_record"].exists())
            self.assertTrue(outputs["review_gate"].exists())
            provenance = json.loads(outputs["provenance"].read_text(encoding="utf-8"))
            self.assertEqual(provenance["original_intelligence"], "medium")
            self.assertEqual(provenance["resolved_intelligence"], "high")
            previous_record = story / provenance["outputs"]["previous_record"]
            self.assertTrue(previous_record.exists())
            explanation = story / "reviews" / "chapter" / "001" / "writer_explanations" / "standard.editor.md"
            self.assertTrue(explanation.exists())
            with self.assertRaisesRegex(RuntimeError, "already been used"):
                rereview_explanation(workspace, "story-1", 1, "editor", "A second explanation.", config)

    def test_rereview_intelligence_must_be_strictly_higher(self) -> None:
        self.assertEqual(
            _rereview_intelligence(
                "medium",
                {"minimum_intelligence": "very_high"},
            ),
            "very_high",
        )
        with self.assertRaisesRegex(ValueError, "higher than the original"):
            _rereview_intelligence("very_high", {})

    def test_rereview_uses_only_routes_above_the_original_intelligence(self) -> None:
        chain = [
            {"profile_name": "low", "resolved_intelligence": "low"},
            {"profile_name": "high", "resolved_intelligence": "high"},
        ]

        self.assertEqual(
            _higher_intelligence_chain(chain, "medium"),
            [chain[1]],
        )
        with self.assertRaisesRegex(ValueError, "no model above"):
            _higher_intelligence_chain(chain[:1], "medium")

    def test_successful_rereview_reports_actual_higher_intelligence(self) -> None:
        self.assertEqual(
            _require_higher_result_intelligence(
                {"resolved_intelligence": "very_high"},
                "high",
            ),
            "very_high",
        )
        with self.assertRaisesRegex(RuntimeError, "not higher"):
            _require_higher_result_intelligence(
                {"resolved_intelligence": "medium"},
                "medium",
            )

    def test_rereview_rejects_reused_codex_thread(self) -> None:
        previous_record = {"session": {"thread_id": "thread-1"}}
        with self.assertRaisesRegex(RuntimeError, "reused Codex thread"):
            _assert_new_rereview_thread(
                previous_record,
                {"session": {"thread_id": "thread-1"}},
            )


if __name__ == "__main__":
    unittest.main()
