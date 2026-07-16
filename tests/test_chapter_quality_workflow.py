from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from shared.lib.review_parser import recommended_gate_status
from tools.review.build_review_pack import build_review_pack
from tools.review.run_review import run_review
from tools.writing.build_write_pack import build_write_pack
from tools.writing.generate_draft import build_generation_prompt, generate_draft


FIXTURES = Path(__file__).parent / "fixtures"


class ChapterQualityWorkflowTests(unittest.TestCase):
    def copy_workspace(self, temp_dir: str) -> Path:
        target = Path(temp_dir) / "workspace"
        shutil.copytree(FIXTURES / "workspace_template", target)
        (target / "workspace.template.yaml").replace(target / "workspace.yaml")
        return target

    def add_active_direction(self, workspace: Path, chapter: int) -> None:
        summaries = workspace / "fixture_stories" / "story-1" / "summaries"
        summaries.mkdir()
        stem = f"chapter_{chapter:03d}"
        (summaries / f"{stem}_brief.md").write_text("# Brief\n\nA decisive confrontation.\n", encoding="utf-8")
        (summaries / f"{stem}_context.md").write_text("# Context\n\nThe prior choice has a cost.\n", encoding="utf-8")
        (summaries / f"{stem}_generation_instruction.md").write_text(
            "# Instruction\n\nDramatize the confrontation through a difficult choice.\n", encoding="utf-8"
        )
        (workspace / "fixture_stories" / "story-1" / "storyline" / "chapter_plan.md").write_text(
            "STALE_GLOBAL_PLAN\n", encoding="utf-8"
        )

    def test_packs_prioritize_active_chapter_direction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            self.add_active_direction(workspace, 2)

            write_pack = build_write_pack(str(workspace), "story-1", 2).read_text(encoding="utf-8")
            review_pack = build_review_pack(str(workspace), "story-1", 2).read_text(encoding="utf-8")

            self.assertIn("Dramatize the confrontation", write_pack)
            self.assertNotIn("STALE_GLOBAL_PLAN", write_pack)
            self.assertIn("Canon Usage Contract", write_pack)
            self.assertIn("private factual reference, not source prose", write_pack)
            self.assertIn("A decisive confrontation", review_pack)
            self.assertIn("The prior choice has a cost", review_pack)

    def test_generation_prompt_separates_canon_constraints_from_scene_prose(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            prompt = build_generation_prompt(str(workspace), "story-1", 1)

            self.assertIn("private constraints, not source prose", prompt)
            self.assertIn("sequence of lived events", prompt)
            self.assertIn("immediate goal, resistance", prompt)
            self.assertIn("Do not label character traits", prompt)

    def test_model_backed_generation_requires_explicit_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            missing_config = Path(temp_dir) / "missing-config.yaml"

            with self.assertRaisesRegex(RuntimeError, "requires an explicit runtime config"):
                generate_draft(str(workspace), "story-1", 1, str(missing_config))

    def test_review_parser_does_not_accept_a_report_without_evidence(self) -> None:
        self.assertEqual(recommended_gate_status("status: pass\ngate_status: accept\n"), "blocked")
        self.assertEqual(
            recommended_gate_status("status: pass\ngate_status: accept\n## Evidence\n- Location: opening\n"),
            "accepted",
        )

    def test_mock_review_writes_current_packet_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            config = FIXTURES / "mock_config.yaml"
            story = workspace / "fixture_stories" / "story-1"
            (story / "reviewers" / "series").mkdir()
            (story / "reviewers" / "special").mkdir()
            (story / "reviewers" / "series" / "timeline.md").write_text("# Series Timeline Reviewer\n", encoding="utf-8")
            (story / "reviewers" / "special" / "director.md").write_text("# Movie Director Reviewer\n", encoding="utf-8")
            (story / "reviewers" / "reviewer_config.yaml").write_text(
                """standard_reviewers:
  continuity:
    enabled: true
    can_block_gate: true
    provider_group: mock_first
series_reviewers:
  timeline:
    enabled: true
    can_block_gate: true
    provider_group: mock_first
    source: reviewers/series/timeline.md
special_reviewers:
  director:
    enabled: true
    can_block_gate: false
    provider_group: mock_first
    source: reviewers/special/director.md
""",
                encoding="utf-8",
            )

            outputs = run_review(str(workspace), "story-1", 1, str(config))

            self.assertTrue((story / "reviews" / "chapter" / "001" / "standard.continuity.md").exists())
            self.assertTrue((story / "reviews" / "chapter" / "001" / "series.timeline.md").exists())
            self.assertTrue((story / "reviews" / "chapter" / "001" / "special.director.md").exists())
            self.assertTrue((story / "runs" / "chapter_001_review.json").exists())
            self.assertIn("evidence-bearing", outputs["review_gate"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
