from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cli.twr import main as cli_main
from tools.writing.revise_draft import REVISION_MODES, build_revision_prompt, revise_draft, revise_scene
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
