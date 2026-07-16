from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from cli.twr import main as cli_main
from shared.lib.workspace_loader import load_workspace
from tools.publish.build_publish_pack import build_publish_pack
from tools.review.build_review_pack import build_review_pack
from tools.review.run_review import run_review
from tools.wizard.scaffold import add_series, add_story, init_workspace
from tools.writing.build_write_pack import build_write_pack
from tools.writing.generate_draft import generate_draft, story_language


FIXTURES = Path(__file__).parent / "fixtures"


class MvpFlowTests(unittest.TestCase):
    def copy_workspace(self, temp_dir: str) -> Path:
        target = Path(temp_dir) / "workspace"
        shutil.copytree(FIXTURES / "workspace_template", target)
        (target / "workspace.template.yaml").replace(target / "workspace.yaml")
        return target

    def test_workspace_fixture_loads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_path = self.copy_workspace(temp_dir)
            workspace = load_workspace(workspace_path)
            self.assertEqual(workspace["stories"], ["story-1"])
            self.assertEqual(workspace["series"], ["series-1"])

    def test_wizard_scaffolds_workspace_story_and_series(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_path = Path(temp_dir) / "new-workspace"

            workspace_yaml = init_workspace(workspace_path, "new-workspace")
            story_path = add_story(workspace_path, "story-a", "Story A", "en")
            series_path = add_series(workspace_path, "series-a", "Series A")

            self.assertTrue(workspace_yaml.exists())
            self.assertTrue((story_path / "canon" / "canon.md").exists())
            self.assertTrue((series_path / "context" / "series_pack.md").exists())

            story_yaml = (story_path / "story.yaml").read_text(encoding="utf-8")
            series_yaml = (series_path / "series.yaml").read_text(encoding="utf-8")
            self.assertIn("id: story-a", story_yaml)
            self.assertIn("title: Story A", story_yaml)
            self.assertIn("primary: en", story_yaml)
            self.assertIn("id: series-a", series_yaml)
            self.assertIn("title: Series A", series_yaml)

            workspace = load_workspace(workspace_path)
            self.assertEqual(workspace["stories"], ["story-a"])
            self.assertEqual(workspace["series"], ["series-a"])

    def test_wizard_refuses_duplicate_story_and_series(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_path = Path(temp_dir) / "new-workspace"

            init_workspace(workspace_path, "new-workspace")
            add_story(workspace_path, "story-a", "Story A", "en")
            add_series(workspace_path, "series-a", "Series A")

            with self.assertRaises(FileExistsError):
                add_story(workspace_path, "story-a", "Story A Duplicate", "en")
            with self.assertRaises(FileExistsError):
                add_series(workspace_path, "series-a", "Series A Duplicate")

    def test_story_language_supports_nested_primary(self) -> None:
        self.assertEqual(story_language({"language": {"primary": "en"}}), "en")
        self.assertEqual(story_language({"language": "zh"}), "zh")

    def test_write_pack_and_mock_draft_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            config = FIXTURES / "mock_config.yaml"

            write_pack = build_write_pack(workspace, "story-1", 1)
            draft = generate_draft(workspace, "story-1", 1, str(config))

            self.assertTrue(write_pack.read_text(encoding="utf-8").startswith("# Write Pack"))
            self.assertTrue(draft.read_text(encoding="utf-8").startswith("# Chapter 1"))

    def test_review_flow_writes_combined_report_and_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            config = FIXTURES / "mock_config.yaml"

            review_pack = build_review_pack(workspace, "story-1", 1)
            outputs = run_review(workspace, "story-1", 1, str(config))

            self.assertIn("Draft Under Review", review_pack.read_text(encoding="utf-8"))
            self.assertTrue(outputs["combined_review"].exists())
            self.assertIn("Gate Status: accepted", outputs["review_gate"].read_text(encoding="utf-8"))

    def test_publish_pack_prefers_accepted_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            publish_pack = build_publish_pack(workspace, "story-1", 1)

            text = publish_pack.read_text(encoding="utf-8")
            self.assertIn("Source Type: accepted", text)
            self.assertIn("accepted fixture chapter", text)

    def test_cli_smoke_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            config = str(FIXTURES / "mock_config.yaml")

            self.assertEqual(cli_main(["config", "validate", "--config", config]), 0)
            self.assertEqual(cli_main(["doctor", "--config", config, "--workspace", str(workspace)]), 0)
            self.assertEqual(
                cli_main(["write", "pack", "--workspace", str(workspace), "--story", "story-1", "--chapter", "1"]),
                0,
            )
            self.assertEqual(
                cli_main(["review", "pack", "--workspace", str(workspace), "--story", "story-1", "--chapter", "1"]),
                0,
            )
            self.assertEqual(
                cli_main(["publish", "pack", "--workspace", str(workspace), "--story", "story-1", "--chapter", "1"]),
                0,
            )

    def test_cli_wizard_smoke_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "cli-workspace"

            self.assertEqual(
                cli_main(["wizard", "workspace", "init", "--workspace", str(workspace), "--workspace-id", "cli"]),
                0,
            )
            self.assertEqual(
                cli_main(
                    [
                        "wizard",
                        "story",
                        "add",
                        "--workspace",
                        str(workspace),
                        "--story",
                        "story-cli",
                        "--title",
                        "CLI Story",
                        "--language",
                        "en",
                    ]
                ),
                0,
            )
            self.assertEqual(
                cli_main(
                    [
                        "wizard",
                        "series",
                        "add",
                        "--workspace",
                        str(workspace),
                        "--series",
                        "series-cli",
                        "--title",
                        "CLI Series",
                    ]
                ),
                0,
            )


if __name__ == "__main__":
    unittest.main()
