from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared.lib.revision_evidence import build_revision_receipt, revision_receipt_path
from tools.review.run_review import rebuild_review_gate, run_review
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

    def test_failed_grounding_repair_writes_no_acceptance_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = str(FIXTURES / "mock_config.yaml")
            run_review(workspace, "story-1", 1, config)
            watched = [
                story / "chapters" / "chapter_001.md",
                story / "summaries" / "summary_chapter_001.md",
                story / "context" / "handover.md",
                story / "state" / "chapter_status.yaml",
                story / "state" / "story_status.yaml",
            ]
            before = {path: path.read_bytes() if path.exists() else None for path in watched}
            continuity = {
                "schema_version": 1,
                "story_id": "story-1",
                "chapter": 1,
                "summary": {key: [] for key in ("events", "decisions", "discoveries", "relationship_changes", "practical_state", "unresolved_pressure")},
                "handover": {key: [] for key in ("ending_situation", "character_intentions", "relationship_state", "open_pressure", "reader_questions", "continuity_details")},
            }
            ungrounded = {
                "schema_version": 1,
                "story_id": "story-1",
                "chapter": 1,
                "grounded": False,
                "unsupported_claims": ["unsupported"],
                "name_conflicts": [],
                "thinking_trace_detected": False,
            }
            with patch(
                "tools.writing.accept_draft.attempt_structured_model_chain",
                side_effect=[
                    {"ok": True, "value": continuity, "attempts": []},
                    {"ok": True, "value": ungrounded, "attempts": []},
                    {"ok": True, "value": continuity, "attempts": []},
                    {"ok": True, "value": ungrounded, "attempts": []},
                ],
            ):
                with self.assertRaisesRegex(RuntimeError, "remained ungrounded"):
                    accept_draft(workspace, "story-1", 1, config)

            self.assertEqual(
                {path: path.read_bytes() if path.exists() else None for path in watched},
                before,
            )
            failure = json.loads((story / "runs" / "chapter_001_acceptance.json").read_text(encoding="utf-8"))
            self.assertEqual(failure["status"], "failed")
            self.assertEqual(failure["failed_stage"], "acceptance_grounding_recheck")

    def test_accept_rejects_a_handwritten_gate_without_quality_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            draft = (story / "drafts" / "chapter_001.md").read_text(encoding="utf-8")
            draft_hash = hashlib.sha256(draft.encode("utf-8")).hexdigest()
            gate = story / "reviews" / "chapter" / "001" / "review_gate_status.md"
            gate.parent.mkdir(parents=True, exist_ok=True)
            gate.write_text(
                "# Review Gate\n\n"
                "run_state: complete\n"
                "status: accepted_with_notes\n"
                f"draft_sha256: {draft_hash}\n"
                "review_mode: manual_fallback\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "correctness evidence"):
                accept_draft(workspace, "story-1", 1, str(FIXTURES / "mock_config.yaml"))

    def test_accept_requires_current_canonical_reviewer_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = str(FIXTURES / "mock_config.yaml")
            run_review(workspace, "story-1", 1, config)
            (story / "reviews" / "chapter" / "001" / "standard.editor.json").unlink()

            with self.assertRaisesRegex(RuntimeError, "canonical review record is missing: standard.editor"):
                accept_draft(workspace, "story-1", 1, config)

    def test_accept_rejects_a_claimed_resolution_without_reviewer_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = str(FIXTURES / "mock_config.yaml")
            outputs = run_review(workspace, "story-1", 1, config)
            draft_hash = hashlib.sha256(
                (story / "drafts" / "chapter_001.md").read_bytes()
            ).hexdigest()
            receipt = build_revision_receipt(
                "story-1",
                1,
                "revision-run",
                "a" * 64,
                draft_hash,
                [
                    {
                        "key": "standard.editor:R001",
                        "reviewer": {"id": "editor", "type": "standard"},
                        "issue_id": "R001",
                    }
                ],
            )
            receipt_path = revision_receipt_path(story, 1)
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            gate_path = outputs["review_gate"]
            gate_path.write_text(
                gate_path.read_text(encoding="utf-8").replace(
                    "revision_resolution_status: not_required",
                    "revision_resolution_status: pass",
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "resolution does not match"):
                accept_draft(workspace, "story-1", 1, config)

    def test_failed_reviewer_preserves_current_records_but_blocks_stale_gate_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = str(FIXTURES / "mock_config.yaml")
            run_review(workspace, "story-1", 1, config)
            current = story / "reviews" / "chapter" / "001"
            before = {
                path.name: path.read_bytes()
                for path in current.iterdir()
                if path.is_file() and path.name.startswith(("standard.", "series.", "special."))
            }

            with patch(
                "tools.review.run_review.attempt_structured_model_chain",
                return_value={"ok": False, "attempts": [{"status": "invalid"}]},
            ):
                with self.assertRaisesRegex(RuntimeError, "failed for all configured models"):
                    run_review(workspace, "story-1", 1, config)

            self.assertEqual(
                {
                    path.name: path.read_bytes()
                    for path in current.iterdir()
                    if path.is_file() and path.name.startswith(("standard.", "series.", "special."))
                },
                before,
            )
            with self.assertRaisesRegex(RuntimeError, "no valid current reviewer reports"):
                rebuild_review_gate(workspace, "story-1", 1)


if __name__ == "__main__":
    unittest.main()
