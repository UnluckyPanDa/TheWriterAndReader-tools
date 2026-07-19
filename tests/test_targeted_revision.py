from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.twr import main as cli_main
from tools.review.run_review import rebuild_review_gate, run_review
from tools.writing.diagnose import write_diagnostics
from tools.writing.revise_draft import (
    REVISION_MODES,
    build_revision_prompt,
    revise_draft,
    revise_scene,
    revision_quality_score,
)
from tools.writing.scene_workflow import draft_scene, plan_scenes


FIXTURES = Path(__file__).parent / "fixtures"


class TargetedRevisionTests(unittest.TestCase):
    def copy_workspace(self, temp_dir: str) -> Path:
        target = Path(temp_dir) / "workspace"
        shutil.copytree(FIXTURES / "workspace_template", target)
        (target / "workspace.template.yaml").replace(target / "workspace.yaml")
        return target

    def test_every_revision_mode_has_a_scoped_prompt(self) -> None:
        for mode in REVISION_MODES:
            prompt = build_revision_prompt(
                "story-1",
                1,
                "en",
                "# Chapter 1",
                mode,
                "# Chapter 1\n\nDraft.",
                "# Write Pack",
                {"flags": {}},
                "",
            )
            self.assertIn(f"revision_mode: {mode}", prompt)
            self.assertIn("Apply only the requested revision mode", prompt)
            self.assertIn("Do not add characters", prompt)

    def test_revision_prompt_accepts_a_variation_factor(self) -> None:
        prompt = build_revision_prompt(
            "story-1",
            1,
            "en",
            "# Chapter 1",
            "prose-polish",
            "# Chapter 1\n\nDraft.",
            "# Write Pack",
            {"metrics": {}},
            "",
            variation_seed=123,
            variation_factor=0.7,
        )

        self.assertIn("variation_seed: 123", prompt)
        self.assertIn("variation_factor: 0.7", prompt)

    def test_revision_quality_score_penalizes_repetition(self) -> None:
        self.assertGreater(
            revision_quality_score({"metrics": {"repeated_phrase_count": 4}}),
            revision_quality_score({"metrics": {"repeated_phrase_count": 1}}),
        )

    def test_mock_revision_records_mode_and_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = FIXTURES / "mock_config.yaml"

            output = revise_draft(workspace, "story-1", 1, "compress", str(config))
            provenance = json.loads((story / "runs" / "chapter_001_revision.json").read_text(encoding="utf-8"))

            self.assertEqual(provenance["revision_mode"], "compress")
            self.assertTrue((story / provenance["outputs"]["source_draft"]).exists())
            self.assertTrue((story / provenance["outputs"]["diagnostics_before"]).exists())
            self.assertTrue((story / provenance["outputs"]["diagnostics_after"]).exists())
            self.assertEqual(output.resolve(), (story / "drafts" / "chapter_001.md").resolve())

    def test_revision_can_keep_best_of_multiple_variations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = FIXTURES / "mock_config.yaml"

            revise_draft(
                workspace,
                "story-1",
                1,
                "prose-polish",
                str(config),
                {"attempts": 3, "temperature": 0.9},
            )
            provenance = json.loads((story / "runs" / "chapter_001_revision.json").read_text(encoding="utf-8"))

            self.assertEqual(provenance["variation_attempts"], 3)
            self.assertEqual(len(provenance["candidate_scores"]), 3)

    def test_revision_never_reports_success_while_keeping_the_original_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = FIXTURES / "mock_config.yaml"
            draft_path = story / "drafts" / "chapter_001.md"
            original = draft_path.read_text(encoding="utf-8")
            revised = "# Chapter 1\n\nA generated revision that directly addresses the reviewer feedback.\n"

            with (
                patch(
                    "tools.writing.revise_draft.attempt_model_chain",
                    return_value={"ok": True, "text": revised, "attempts": []},
                ),
                patch(
                    "tools.writing.revise_draft.revision_quality_score",
                    side_effect=[1.0, 9.0],
                ),
            ):
                revise_draft(workspace, "story-1", 1, "prose-polish", str(config))

            self.assertNotEqual(draft_path.read_text(encoding="utf-8"), original)
            self.assertEqual(draft_path.read_text(encoding="utf-8"), revised)

    def test_failed_revision_writes_durable_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = FIXTURES / "mock_config.yaml"

            with patch(
                "tools.writing.revise_draft.attempt_model_chain",
                return_value={"ok": False, "attempts": [{"status": "unreachable"}]},
            ):
                with self.assertRaisesRegex(RuntimeError, "failed for all configured models"):
                    revise_draft(workspace, "story-1", 1, "deepen", str(config))

            provenance = json.loads(
                (story / "runs" / "chapter_001_revision.json").read_text(encoding="utf-8")
            )
            self.assertEqual(provenance["status"], "failed")
            self.assertEqual(provenance["failed_stage"], "chapter_revision")
            self.assertEqual(provenance["attempts"], [{"status": "unreachable"}])

    def test_revision_issues_require_explicit_fresh_reviewer_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = FIXTURES / "mock_config.yaml"
            run_review(workspace, "story-1", 1, str(config))
            editor_path = story / "reviews" / "chapter" / "001" / "standard.editor.json"
            editor = json.loads(editor_path.read_text(encoding="utf-8"))
            editor["decision"].update(
                {
                    "status": "needs_revision",
                    "summary": "The middle scene summarizes its dramatic turn.",
                    "severity_counts": {"blocker": 0, "major": 1, "minor": 0, "note": 0},
                    "issues": [
                        {
                            "issue_id": "R001",
                            "issue_type": "summary_instead_of_scene",
                            "severity": "major",
                            "location": "middle scene",
                            "observation": "The refusal is reported after it happens.",
                            "reader_effect": "The central turn feels remote.",
                            "review_scope": "scene",
                            "rewrite_required": True,
                            "rewrite_scope": "scene",
                            "suggested_fix": "Dramatize the refusal and immediate consequence.",
                        }
                    ],
                    "rewrite_recommendation": {"required": True, "scope": "scene"},
                    "gate_recommendation": "revise",
                    "reviewer_notes": [],
                }
            )
            editor_path.write_text(json.dumps(editor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            rebuild_review_gate(workspace, "story-1", 1)

            revise_draft(workspace, "story-1", 1, "deepen", str(config))
            revise_draft(workspace, "story-1", 1, "prose-polish", str(config))

            receipt_path = story / "reviews" / "chapter" / "001" / "revision_issue_receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [issue["key"] for issue in receipt["required_issues"]],
                ["standard.editor:R001"],
            )
            provenance = json.loads(
                (story / "runs" / "chapter_001_revision.json").read_text(encoding="utf-8")
            )
            after = json.loads(
                (story / provenance["outputs"]["diagnostics_after"]).read_text(encoding="utf-8")
            )
            self.assertEqual(after["draft_sha256"], receipt["revised_draft_sha256"])
            write_diagnostics(workspace, "story-1", 1)
            outputs = run_review(workspace, "story-1", 1, str(config))
            current_editor = json.loads(editor_path.read_text(encoding="utf-8"))

            self.assertIn("resolved_prior_issue:R001", current_editor["decision"]["reviewer_notes"])
            self.assertIn(
                "revision_resolution_status: pass",
                outputs["review_gate"].read_text(encoding="utf-8"),
            )

            current_editor["decision"]["reviewer_notes"] = ["Marker removed."]
            editor_path.write_text(
                json.dumps(current_editor, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            rebuilt = rebuild_review_gate(workspace, "story-1", 1)
            gate = rebuilt["review_gate"].read_text(encoding="utf-8")
            self.assertIn("revision_resolution_status: incomplete", gate)
            self.assertIn("unresolved_revision_issues: standard.editor:R001", gate)
            self.assertIn("status: blocked", gate)

    def test_cli_diagnose_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"

            result = cli_main(
                [
                    "write",
                    "diagnose",
                    "--workspace",
                    str(workspace),
                    "--story",
                    "story-1",
                    "--chapter",
                    "1",
                ]
            )

            self.assertEqual(result, 0)
            self.assertTrue((story / "context" / "chapter_001_writing_diagnostics.json").exists())

    def test_scene_revision_changes_only_the_selected_scene_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = str(FIXTURES / "mock_config.yaml")
            plan_scenes(workspace, "story-1", 1, config)
            scene_path = draft_scene(workspace, "story-1", 1, "scene-1", config)
            chapter_before = (story / "drafts" / "chapter_001.md").read_text(encoding="utf-8")

            output = revise_scene(workspace, "story-1", 1, "scene-1", "de-duplicate", config)

            self.assertEqual(output, scene_path)
            self.assertTrue(output.read_text(encoding="utf-8").strip())
            self.assertEqual((story / "drafts" / "chapter_001.md").read_text(encoding="utf-8"), chapter_before)


if __name__ == "__main__":
    unittest.main()
