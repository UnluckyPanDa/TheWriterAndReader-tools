from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared.lib.review_parser import recommended_gate_status, validate_review_report
from shared.lib.scene_contract import parse_scene_contract
from shared.lib.scene_skeleton import parse_scene_skeleton
from tools.review.build_review_pack import build_review_pack
from tools.review.run_review import _novelness_status, run_novelness_gate, run_review
from tools.publish.build_publish_pack import build_publish_pack
from tools.writing.build_write_pack import build_write_pack
from tools.writing.generate_draft import build_generation_prompt, build_polish_prompt, generate_draft


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
            self.assertIn("wording_reuse_allowed: false", write_pack)
            self.assertIn("Context Selection Contract", write_pack)
            self.assertIn("Viewpoint Usage Contract", write_pack)
            self.assertIn("Active Story and Chapter State", write_pack)
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

    def test_generation_prompt_rebuilds_stale_pack_and_excludes_unaccepted_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            (story / "context" / "write_pack.md").write_text("STALE_PACK_FOR_CHAPTER_99\n", encoding="utf-8")
            (story / "drafts" / "chapter_001.md").write_text("UNACCEPTED_STYLE_PHRASE\n", encoding="utf-8")

            prompt = build_generation_prompt(str(workspace), "story-1", 2)

            self.assertNotIn("STALE_PACK_FOR_CHAPTER_99", prompt)
            self.assertNotIn("UNACCEPTED_STYLE_PHRASE", prompt)
            self.assertIn("- Chapter: 2", prompt)

    def test_write_pack_uses_the_configured_writer_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            story_yaml = story / "story.yaml"
            story_yaml.write_text(story_yaml.read_text(encoding="utf-8") + "\nwriter:\n  profile: writer/custom.md\n", encoding="utf-8")
            (story / "writer" / "custom.md").write_text("CUSTOM_WRITER_PROFILE\n", encoding="utf-8")

            write_pack = build_write_pack(str(workspace), "story-1", 1).read_text(encoding="utf-8")

            self.assertIn("CUSTOM_WRITER_PROFILE", write_pack)

    def test_scene_contract_requires_a_real_state_change(self) -> None:
        valid = {
            "schema_version": 1,
            "story_id": "story-1",
            "chapter": 1,
            "chapter_progression": {
                "plot": "The practical problem changes.",
                "character": "The protagonist commits.",
                "mystery": "A new question opens.",
            },
            "scenes": [
                {
                    "scene_id": "scene-1",
                    "viewpoint_character": "protagonist",
                    "starting_state": "The choice is open.",
                    "immediate_goal": "Obtain an answer.",
                    "pressure": "Time is running out.",
                    "opposition": "The witness refuses.",
                    "change_axes": ["knowledge"],
                    "required_change": "The protagonist learns the cost.",
                    "new_information": "The answer creates a cost.",
                    "physical_setting": "Test room.",
                    "active_characters": ["protagonist"],
                    "required_beats": ["The witness interrupts the plan."],
                    "forbidden_reveals": [],
                    "ending_turn": "The answer creates a new obligation.",
                }
            ],
        }

        self.assertEqual(parse_scene_contract(json.dumps(valid), "story-1", 1), valid)
        valid["scenes"][0]["change_axes"] = []
        with self.assertRaisesRegex(ValueError, "invalid scene contract"):
            parse_scene_contract(json.dumps(valid), "story-1", 1)

    def test_scene_skeleton_must_match_contract_order(self) -> None:
        skeleton = {
            "schema_version": 1,
            "story_id": "story-1",
            "chapter": 1,
            "scenes": [
                {
                    "scene_id": "scene-1",
                    "purpose": "Force a choice.",
                    "entry_condition": "The answer is unavailable.",
                    "action_sequence": ["The protagonist asks for the answer."],
                    "conflict_escalation": ["The witness refuses."],
                    "emotional_turns": ["Certainty gives way to doubt."],
                    "exit_condition": "The refusal creates a new obligation.",
                }
            ],
        }

        self.assertEqual(parse_scene_skeleton(json.dumps(skeleton), "story-1", 1, ["scene-1"]), skeleton)
        with self.assertRaisesRegex(ValueError, "must match the scene contract in order"):
            parse_scene_skeleton(json.dumps(skeleton), "story-1", 1, ["scene-2"])

    def test_polish_prompt_forbids_plot_changes(self) -> None:
        prompt = build_polish_prompt(
            "story-1",
            1,
            "en",
            "# Chapter 1",
            {"scenes": []},
            "# Chapter 1\n\nFirst draft.",
        )

        self.assertIn("Do not add plot facts", prompt)
        self.assertIn("Remove repeated meanings", prompt)
        self.assertIn("Keep the chapter heading exactly", prompt)

    def test_model_backed_generation_requires_explicit_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            missing_config = Path(temp_dir) / "missing-config.yaml"

            with self.assertRaisesRegex(RuntimeError, "requires an explicit runtime config"):
                generate_draft(str(workspace), "story-1", 1, str(missing_config))

    def test_review_parser_does_not_accept_a_report_without_evidence(self) -> None:
        self.assertEqual(recommended_gate_status("status: pass\ngate_status: accept\n"), "blocked")
        self.assertEqual(
            recommended_gate_status(
                "status: pass\ngate_status: accept\n## Evidence\n"
                "- Location: opening\n  Observation: active pressure\n  Reader effect: immediate pull\n"
            ),
            "accepted",
        )

    def test_review_contract_requires_complete_evidence(self) -> None:
        report = """# Review Report
reviewer_id: editor
reviewer_type: standard
story_id: story-1
chapter: 1
status: pass
## Summary
Clear.
## Evidence
- Location: opening
  Observation: the scene starts in motion
## Severity Counts
- blocker: 0
- major: 0
- minor: 0
- note: 0
## Issues
## Rewrite Recommendation
rewrite_required: no
rewrite_scope: none
## Gate Recommendation
gate_status: accept
"""
        self.assertIn("evidence reader effect", validate_review_report(report, "editor"))

    def test_mock_generation_writes_multi_pass_artifacts_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            story = workspace / "fixture_stories" / "story-1"
            config = FIXTURES / "mock_config.yaml"

            generate_draft(str(workspace), "story-1", 1, str(config))

            provenance = json.loads((story / "runs" / "chapter_001_generation.json").read_text(encoding="utf-8"))
            contract_path = story / provenance["outputs"]["scene_contract"]
            skeleton_path = story / provenance["outputs"]["scene_skeleton"]
            first_draft_path = story / provenance["outputs"]["first_draft"]
            deepened_draft_path = story / provenance["outputs"]["deepened_draft"]
            compressed_draft_path = story / provenance["outputs"]["compressed_draft"]
            diagnostics_path = story / provenance["outputs"]["diagnostics"]
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            skeleton = json.loads(skeleton_path.read_text(encoding="utf-8"))
            self.assertEqual(contract["chapter"], 1)
            self.assertIn("active_canon", provenance["context_tokens_by_category"])
            self.assertEqual(provenance["generation_pass"], "voice_polish_complete")
            self.assertIn("repeated_phrase_count", provenance["writing_metrics"])
            self.assertEqual([scene["scene_id"] for scene in skeleton["scenes"]], ["scene-1"])
            self.assertTrue(first_draft_path.read_text(encoding="utf-8").startswith("# Chapter 1"))
            self.assertTrue(deepened_draft_path.read_text(encoding="utf-8").startswith("# Chapter 1"))
            self.assertTrue(compressed_draft_path.read_text(encoding="utf-8").startswith("# Chapter 1"))
            self.assertEqual(list(provenance["outputs"]["scene_drafts"]), ["scene-1"])
            self.assertEqual(json.loads(diagnostics_path.read_text(encoding="utf-8"))["chapter"], 1)
            self.assertEqual(
                [stage["name"] for stage in provenance["stages"]],
                [
                    "scene_planning",
                    "scene_skeleton",
                    "scene_first_drafts",
                    "narrative_deepening",
                    "de_duplication",
                    "prose_polish",
                ],
            )
            self.assertTrue((contract_path.parent / "generation.json").exists())

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
            self.assertIn("novelness_status: incomplete", outputs["review_gate"].read_text(encoding="utf-8"))
            self.assertIn("status: incomplete", outputs["novelness_gate"].read_text(encoding="utf-8"))

    def test_required_reviewers_produce_independent_acceptance_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            config = FIXTURES / "mock_config.yaml"

            outputs = run_review(str(workspace), "story-1", 1, str(config))
            gate = outputs["review_gate"].read_text(encoding="utf-8")

            self.assertIn("correctness_status: pass", gate)
            self.assertIn("novelness_status: accept", gate)
            self.assertIn("status: accepted", gate)
            self.assertIn("status: accept", outputs["novelness_gate"].read_text(encoding="utf-8"))
            rebuilt = run_novelness_gate(workspace, "story-1", 1)
            self.assertIn("status: accept", rebuilt.read_text(encoding="utf-8"))

    def test_novelness_gate_maps_a_major_scene_issue_to_scene_rewrite(self) -> None:
        rows = []
        for reviewer_id in ("editor", "pacing", "tone", "character"):
            is_editor = reviewer_id == "editor"
            rows.append(
                {
                    "layer": "standard",
                    "reviewer_id": reviewer_id,
                    "can_block": True,
                    "decision": "revision_recommended" if is_editor else "accepted",
                    "counts": {"blocker": 0, "major": 1 if is_editor else 0, "minor": 0, "note": 0},
                    "rewrite_scope": "scene" if is_editor else "none",
                }
            )

        self.assertEqual(_novelness_status(rows), ("scene_rewrite", []))

    def test_novelness_gate_rejects_deterministic_source_copying(self) -> None:
        rows = [
            {
                "layer": "standard",
                "reviewer_id": reviewer_id,
                "can_block": True,
                "decision": "accepted",
                "counts": {"blocker": 0, "major": 0, "minor": 0, "note": 0},
                "rewrite_scope": "none",
            }
            for reviewer_id in ("editor", "pacing", "tone", "character")
        ]

        self.assertEqual(
            _novelness_status(rows, {"metrics": {"exact_source_phrase_count": 1}}),
            ("targeted_revision", []),
        )
        self.assertEqual(
            _novelness_status(rows, {"metrics": {"semantic_repetition_count": 1}}),
            ("targeted_revision", []),
        )

    def test_failed_rerun_invalidates_an_older_accepted_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            config = FIXTURES / "mock_config.yaml"
            story = workspace / "fixture_stories" / "story-1"
            run_review(str(workspace), "story-1", 1, str(config))

            with patch("tools.review.run_review.attempt_model_chain", return_value={"ok": False, "attempts": []}):
                with self.assertRaisesRegex(RuntimeError, "failed for all configured models"):
                    run_review(str(workspace), "story-1", 1, str(config))

            gate = story / "reviews" / "chapter" / "001" / "review_gate_status.md"
            gate_text = gate.read_text(encoding="utf-8")
            self.assertIn("run_state: failed", gate_text)
            self.assertIn("status: blocked", gate_text)

    def test_publish_pack_rejects_a_gate_for_an_older_draft_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            config = FIXTURES / "mock_config.yaml"
            story = workspace / "fixture_stories" / "story-1"
            (story / "chapters" / "chapter_001.md").unlink()
            run_review(str(workspace), "story-1", 1, str(config))
            (story / "drafts" / "chapter_001.md").write_text("# Chapter 1\n\nChanged after review.\n", encoding="utf-8")

            publish_pack = build_publish_pack(str(workspace), "story-1", 1).read_text(encoding="utf-8")

            self.assertIn("changed after its accepted review", publish_pack)


if __name__ == "__main__":
    unittest.main()
