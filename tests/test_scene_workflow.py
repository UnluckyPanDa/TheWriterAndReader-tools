from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.twr import main as cli_main
from tools.review.build_review_pack import build_review_pack
from tools.writing.generate_draft import StructuredOutputFailure
from tools.writing.scene_workflow import assemble_chapter, draft_scene, plan_scenes


FIXTURES = Path(__file__).parent / "fixtures"


class SceneWorkflowTests(unittest.TestCase):
    def copy_workspace(self, temp_dir: str) -> Path:
        target = Path(temp_dir) / "workspace"
        shutil.copytree(FIXTURES / "workspace_template", target)
        (target / "workspace.template.yaml").replace(target / "workspace.yaml")
        return target

    def test_plan_draft_and_assemble_scene_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = str(FIXTURES / "mock_config.yaml")

            plan = plan_scenes(workspace, "story-1", 1, config)
            scene = draft_scene(workspace, "story-1", 1, "scene-1", config)
            chapter = assemble_chapter(workspace, "story-1", 1)
            review_pack = build_review_pack(workspace, "story-1", 1).read_text(encoding="utf-8")

            self.assertTrue(plan["scene_contract"].exists())
            self.assertTrue(plan["scene_skeleton"].exists())
            self.assertEqual(scene.parent.name, "chapter_001_scenes")
            self.assertTrue(chapter.read_text(encoding="utf-8").startswith("# Chapter 1"))
            self.assertTrue((story / "runs" / "chapter_001_scene_planning.json").exists())
            self.assertIn('"scene_id": "scene-1"', review_pack)

    def test_cli_scene_workflow_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            config = str(FIXTURES / "mock_config.yaml")
            common = ["--workspace", str(workspace), "--story", "story-1", "--chapter", "1"]

            self.assertEqual(cli_main(["write", "plan-scene", *common, "--config", config]), 0)
            self.assertEqual(
                cli_main(["write", "draft-scene", *common, "--scene", "scene-1", "--config", config]),
                0,
            )
            self.assertEqual(cli_main(["write", "assemble-chapter", *common]), 0)

    def test_assemble_fails_when_a_planned_scene_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            config = str(FIXTURES / "mock_config.yaml")
            plan_scenes(workspace, "story-1", 1, config)

            with self.assertRaisesRegex(FileNotFoundError, "missing scene drafts"):
                assemble_chapter(workspace, "story-1", 1)

    def test_failed_scene_contract_repair_writes_raw_response_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            invalid_initial = '{"story_id":"story-2"}'
            invalid_repair = "RAW_REPAIR_SENTINEL"
            failure_result = {
                "ok": False,
                "text": "",
                "model_profile": None,
                "attempts": [
                    {
                        "model_profile": "local_writer",
                        "status": "invalid",
                        "structured_output_phase": "initial",
                        "validation_status": "invalid",
                        "response_text": invalid_initial,
                    },
                    {
                        "model_profile": "local_writer",
                        "status": "invalid",
                        "structured_output_phase": "repair",
                        "validation_status": "invalid",
                        "response_text": invalid_repair,
                    },
                ],
            }
            failure = StructuredOutputFailure(
                "scene contract remained invalid after one repair",
                "scene_contract",
                failure_result,
            )

            with patch(
                "tools.writing.scene_workflow.generate_scene_contract",
                side_effect=failure,
            ):
                with self.assertRaises(StructuredOutputFailure):
                    plan_scenes(
                        workspace,
                        "story-1",
                        1,
                        str(FIXTURES / "mock_config.yaml"),
                    )

            provenance_path = story / "runs" / "chapter_001_scene_planning.json"
            provenance_text = provenance_path.read_text(encoding="utf-8")
            provenance = json.loads(provenance_text)
            self.assertEqual(provenance["status"], "failed")
            self.assertEqual(provenance["failure_stage"], "scene_contract")
            self.assertNotIn("response_text", provenance_text)
            self.assertNotIn("RAW_REPAIR_SENTINEL", provenance_text)
            response_paths = [
                story / attempt["response_artifact"] for attempt in provenance["attempts"]
            ]
            self.assertEqual(
                [path.read_text(encoding="utf-8") for path in response_paths],
                [invalid_initial, invalid_repair],
            )
            self.assertEqual(
                [attempt["response_characters"] for attempt in provenance["attempts"]],
                [len(invalid_initial), len(invalid_repair)],
            )


if __name__ == "__main__":
    unittest.main()
