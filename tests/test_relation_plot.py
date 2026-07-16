from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cli.twr import main as cli_main
from shared.lib.relationship_graph import relationship_graph_summary, validate_relationship_graph
from shared.lib.yaml_utils import dump_yaml
from tools.wizard.relation_plot import build_relation_plot, init_relation_plot
from tools.wizard.scaffold import add_story, init_workspace


class RelationshipPlotTests(unittest.TestCase):
    def create_story(self, temp_dir: str) -> tuple[Path, Path]:
        workspace = Path(temp_dir) / "workspace"
        init_workspace(workspace, "relations")
        story = add_story(workspace, "story-1", "Relation Story", "en")
        return workspace, story

    def sample_graph(self) -> dict:
        return {
            "version": 1,
            "characters": [
                {"id": "ada", "label": "Ada", "group": "Crew"},
                {"id": "lin", "label": "Lin", "group": "Crew", "position": {"x": 2, "y": 4, "z": 8}},
            ],
            "relationships": [
                {
                    "id": "ada-trusts-lin",
                    "source": "ada",
                    "target": "lin",
                    "type": "trust",
                    "strength": 0.8,
                    "direction": "outgoing",
                    "visibility": {"start_chapter": 2, "end_chapter": None},
                }
            ],
        }

    def test_new_story_contains_empty_relationship_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _, story = self.create_story(temp_dir)
            graph = story / "canon" / "relationship_graph.yaml"
            self.assertTrue(graph.exists())
            self.assertIn("version: 1", graph.read_text(encoding="utf-8"))

    def test_init_refuses_to_overwrite_existing_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace, _ = self.create_story(temp_dir)
            with self.assertRaises(FileExistsError):
                init_relation_plot(workspace, "story-1")

    def test_init_adds_graph_to_existing_story_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace, story = self.create_story(temp_dir)
            graph = story / "canon" / "relationship_graph.yaml"
            graph.unlink()

            output = init_relation_plot(workspace, "story-1")

            self.assertEqual(output, graph)
            self.assertIn("relationships: []", graph.read_text(encoding="utf-8"))

    def test_validation_rejects_unknown_character_and_bad_visibility(self) -> None:
        graph = self.sample_graph()
        graph["relationships"][0]["target"] = "missing"
        graph["relationships"][0]["visibility"] = {"start_chapter": 4, "end_chapter": 2}

        with self.assertRaises(ValueError) as context:
            validate_relationship_graph(graph)

        message = str(context.exception)
        self.assertIn("unknown character 'missing'", message)
        self.assertIn("end_chapter must be at least start_chapter", message)

    def test_build_writes_self_contained_interactive_viewer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace, story = self.create_story(temp_dir)
            graph_path = story / "canon" / "relationship_graph.yaml"
            graph_path.write_text(dump_yaml(self.sample_graph(), sort_keys=False), encoding="utf-8")

            output = build_relation_plot(workspace, "story-1")
            text = output.read_text(encoding="utf-8")

            self.assertEqual(output, story / "build" / "relation-plot" / "index.html")
            self.assertIn("Relation Story — Relationship Plot", text)
            self.assertIn('id="plot"', text)
            self.assertIn('"ada-trusts-lin"', text)
            self.assertNotIn("https://", text)

    def test_summary_respects_chapter_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _, story = self.create_story(temp_dir)
            (story / "canon" / "relationship_graph.yaml").write_text(
                dump_yaml(self.sample_graph(), sort_keys=False), encoding="utf-8"
            )

            self.assertIn("No structured relationships", relationship_graph_summary(story, 1))
            self.assertIn("Ada -> Lin: trust", relationship_graph_summary(story, 2))

    def test_cli_builds_relation_plot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace, story = self.create_story(temp_dir)
            (story / "canon" / "relationship_graph.yaml").write_text(
                dump_yaml(self.sample_graph(), sort_keys=False), encoding="utf-8"
            )

            result = cli_main(
                ["wizard", "relation-plot", "build", "--workspace", str(workspace), "--story", "story-1"]
            )

            self.assertEqual(result, 0)
            self.assertTrue((story / "build" / "relation-plot" / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
