from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.writing.diagnose import analyze_draft, write_diagnostics


FIXTURES = Path(__file__).parent / "fixtures"


class WritingDiagnosticsTests(unittest.TestCase):
    def copy_workspace(self, temp_dir: str) -> Path:
        target = Path(temp_dir) / "workspace"
        shutil.copytree(FIXTURES / "workspace_template", target)
        (target / "workspace.template.yaml").replace(target / "workspace.yaml")
        return target

    def test_diagnostics_flag_source_reuse_and_repeated_paragraphs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            source_phrase = "the brass key remained under the cracked blue cup beside the window"
            (story / "canon" / "canon.md").write_text(source_phrase + "\n", encoding="utf-8")
            draft = (
                "# Chapter 1\n\n"
                + source_phrase
                + ".\n\nThe witness watched the locked door while the storm crossed the empty yard.\n\n"
                "The witness watched the locked door while the storm crossed the empty yard.\n"
            )
            (story / "drafts" / "chapter_001.md").write_text(draft, encoding="utf-8")

            result = analyze_draft(story, 1)

            self.assertGreater(result["metrics"]["exact_source_phrase_count"], 0)
            self.assertEqual(result["metrics"]["semantic_repetition_count"], 1)
            self.assertGreater(result["metrics"]["repeated_phrase_count"], 0)
            self.assertIn("exposition_concentration", result["metrics"])
            self.assertIn("reviewer_issue_count", result["metrics"])
            self.assertTrue(result["flags"]["repeated_openings"])

    def test_diagnostics_write_inside_story_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)

            output = write_diagnostics(workspace, "story-1", 1)
            payload = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(output.name, "chapter_001_writing_diagnostics.json")
            self.assertEqual(payload["chapter"], 1)
            self.assertIn("paragraph_functions", payload)
            draft = (workspace / "fixture_stories" / "story-1" / "drafts" / "chapter_001.md").read_text(
                encoding="utf-8"
            )
            self.assertEqual(payload["draft_sha256"], hashlib.sha256(draft.encode("utf-8")).hexdigest())

    def test_current_chapter_reviews_are_not_source_similarity_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            phrase = "review quotation should not become a source reuse penalty"
            draft = f"# Chapter 1\n\n{phrase}.\n"
            (story / "drafts" / "chapter_001.md").write_text(draft, encoding="utf-8")
            review_root = story / "reviews" / "chapter" / "001"
            review_root.mkdir(parents=True, exist_ok=True)
            (review_root / "standard.editor.md").write_text(phrase + "\n", encoding="utf-8")

            result = analyze_draft(story, 1, exact_min_words=8, distinctive_min_words=5)

            self.assertFalse(
                any(
                    flag["source"] == "reviews/chapter/001/standard.editor.md"
                    for flag in result["flags"]["distinctive_source_phrases"]
                )
            )

    def test_configured_world_terms_are_exempt_from_source_similarity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            story_yaml = story / "story.yaml"
            story_yaml.write_text(
                story_yaml.read_text(encoding="utf-8")
                + "\nwriting_diagnostics:\n  source_similarity_exemptions:\n    - Alpha Beta Gamma Delta Epsilon\n",
                encoding="utf-8",
            )
            phrase = "Alpha Beta Gamma Delta Epsilon"
            (story / "canon" / "canon.md").write_text(phrase + "\n", encoding="utf-8")
            (story / "drafts" / "chapter_001.md").write_text("# Chapter 1\n\n" + phrase + "\n", encoding="utf-8")

            result = analyze_draft(story, 1, exact_min_words=5, distinctive_min_words=5)

            self.assertEqual(result["metrics"]["exact_source_phrase_count"], 0)


if __name__ == "__main__":
    unittest.main()
