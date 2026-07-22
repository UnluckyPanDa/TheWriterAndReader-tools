from __future__ import annotations

import json
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared.lib.review_parser import normalize_review_decision, render_review_report, validate_review_report
from shared.lib.review_handoff import (
    _digest,
    apply_review_handoff,
    execute_review_handoff,
    prepare_review_handoff,
)
from tools.writing.generate_draft import StructuredOutputFailure, generate_draft, normalize_generated_draft


FIXTURES = Path(__file__).parent / "fixtures"


class ReviewNormalizationTests(unittest.TestCase):
    def test_accepts_current_fenced_legacy_and_prose_boundaries(self) -> None:
        current = {
            "schema_version": 1,
            "reviewer_id": "wrong",
            "reviewer_type": "standard",
            "story_id": "wrong-story",
            "chapter": 99,
            "status": "pass",
            "summary": "The opening establishes immediate pressure.",
            "evidence": [{"location": "opening", "observation": "The scene begins in motion.", "reader_effect": "The reader understands the pressure."}],
            "severity_counts": {"blocker": 0, "major": 0, "minor": 0, "note": 0},
            "issues": [],
            "rewrite_recommendation": {"required": False, "scope": "none"},
            "gate_recommendation": "accept",
            "carry_forward_tasks": [],
            "reviewer_notes": [],
        }
        for source in (
            json.dumps(current),
            "```json\n" + json.dumps(current) + "\n```",
            """# Review Report
reviewer_id: old
reviewer_type: standard
story_id: old-story
chapter: 1
status: pass
## Summary
The opening establishes pressure.
## Evidence
- Location: opening
  Observation: The scene begins in motion.
  Reader effect: The reader understands the pressure.
## Issues
## Gate Recommendation
gate_status: accept
""",
            "Pass. The opening scene establishes immediate pressure for the reader." ,
        ):
            with self.subTest(source=source[:20]):
                result = normalize_review_decision(source, "editor", "standard", "story-1", 1)
                self.assertEqual(result["canonical"]["reviewer_id"], "editor")
                self.assertEqual(result["canonical"]["story_id"], "story-1")
                self.assertEqual(result["canonical"]["chapter"], 1)
                self.assertEqual(result["canonical"]["gate_recommendation"], "accept")

    def test_accepts_emphasized_review_findings_from_local_model(self) -> None:
        source = """reviewer_id: standard.character
story_id: story-1
chapter: 1
decision: blocked
severity: high

## Review Findings

**Issue #1: Passive opening**
*   **Location:** Opening paragraph
*   **Observation:** The protagonist observes the room without making a choice.
*   **Impact:** The reader experiences narrative stasis instead of pressure.

**Issue #2: Missing turn**
*   **Location:** End of draft
*   **Observation:** The scene ends on an abstract thought instead of a consequence.
*   **Impact:** The ending does not create forward momentum.

## Gate Guidance: BLOCKED
"""

        result = normalize_review_decision(source, "character", "standard", "story-1", 1)
        decision = result["canonical"]
        report = render_review_report(decision)

        self.assertEqual(result["source_format"], "legacy_markdown")
        self.assertEqual(decision["status"], "blocked")
        self.assertEqual(len(decision["issues"]), 2)
        self.assertEqual(decision["severity_counts"]["major"], 2)
        self.assertEqual(decision["gate_recommendation"], "block")
        self.assertEqual(validate_review_report(report, "character"), [])

    def test_accepts_markdown_findings_table_from_local_model(self) -> None:
        source = """reviewer_id: continuity
reviewer_type: standard
story_id: story-1
chapter: 1
decision: revision

### Findings & Issues

| Severity | Location | Observation | Impact | Suggested Fix |
| :--- | :--- | :--- | :--- | :--- |
| **Critical** | Scene start | The entry is stated without action or obstacle. | The reader has no immediate scene tension. | Establish an objective and concrete pressure. |
| **Major** | Scene end | The ending is an abstract thought instead of a consequence. | The chapter does not land on a turn. | End after a specific choice or discovery. |
"""

        result = normalize_review_decision(source, "continuity", "standard", "story-1", 1)
        decision = result["canonical"]

        self.assertEqual(result["source_format"], "legacy_markdown")
        self.assertEqual(decision["status"], "needs_revision")
        self.assertEqual(len(decision["issues"]), 2)
        self.assertEqual(decision["severity_counts"]["blocker"], 1)
        self.assertEqual(decision["severity_counts"]["major"], 1)
        self.assertEqual(validate_review_report(render_review_report(decision), "continuity"), [])

    def test_accepts_issues_found_with_emphasis_outside_colon(self) -> None:
        source = """reviewer_id: standard.continuity
story_id: story-1
chapter: 1
gate_decision: revision

## Issues Found

### Issue 001: Missing objective
- **Location:** Entire draft
- **Observation:** The protagonist enters without an immediate objective.
- **Impact:** The reader has no causal pressure to follow.
- **Severity**: Major

## Gate Guidance
**Decision: Revise Required.**
"""

        result = normalize_review_decision(source, "continuity", "standard", "story-1", 1)
        decision = result["canonical"]

        self.assertEqual(decision["status"], "needs_revision")
        self.assertEqual(len(decision["issues"]), 1)
        self.assertEqual(decision["severity_counts"]["major"], 1)
        self.assertEqual(validate_review_report(render_review_report(decision), "continuity"), [])

    def test_multiline_prose_fallback_renders_as_compatible_report(self) -> None:
        source = """Blocked because the chapter opening has no concrete action.

## Detailed Assessment
The character remains passive, so the reader cannot experience immediate pressure.
"""

        decision = normalize_review_decision(source, "character", "standard", "story-1", 1)["canonical"]

        self.assertEqual(validate_review_report(render_review_report(decision), "character"), [])

    def test_rejects_ambiguous_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "evidence"):
            normalize_review_decision("Looks good.", "editor", "standard", "story-1", 1)

    def test_draft_normalization_keeps_usable_prose(self) -> None:
        normalized = normalize_generated_draft("```markdown\nProse without an exact heading.\n```", "# Chapter 7")
        self.assertEqual(normalized, "# Chapter 7\n\nProse without an exact heading.")

    def test_scene_planning_failure_can_record_unstructured_prose_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            shutil.copytree(FIXTURES / "workspace_template", workspace)
            (workspace / "workspace.template.yaml").replace(workspace / "workspace.yaml")
            failure = StructuredOutputFailure(
                "scene plan was malformed",
                "scene_contract",
                {"attempts": [{"status": "invalid"}]},
            )
            with patch("tools.writing.generate_draft.generate_scene_contract", side_effect=failure), patch(
                "tools.writing.generate_draft.attempt_model_chain",
                return_value={
                    "ok": True,
                    "text": "Plain prose begins without a heading and still contains a usable chapter movement.",
                    "model_profile": "mock_writer",
                    "attempts": [],
                },
            ):
                output = generate_draft(workspace, "story-1", 1, str(FIXTURES / "mock_config.yaml"))
            self.assertTrue(output.exists())
            provenance = json.loads(
                (workspace / "fixture_stories" / "story-1" / "runs" / "chapter_001_generation.json").read_text(encoding="utf-8")
            )
            self.assertEqual(provenance["generation_pass"], "unstructured_planning_fallback")
            self.assertEqual(provenance["planning_fallback"]["mode"], "unstructured_prose")


class ReviewHandoffTests(unittest.TestCase):
    def copy_workspace(self, temp_dir: str) -> Path:
        target = Path(temp_dir) / "workspace"
        shutil.copytree(FIXTURES / "workspace_template", target)
        (target / "workspace.template.yaml").replace(target / "workspace.yaml")
        return target

    def test_prepare_execute_apply_and_idempotent_reapply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            config = str(FIXTURES / "mock_config.yaml")
            request = prepare_review_handoff(workspace, "story-1", 1)
            result = execute_review_handoff(workspace, "story-1", 1, request, config)
            story = workspace / "fixture_stories" / "story-1"
            review_root = story / "reviews" / "chapter" / "001"
            self.assertFalse((review_root / "standard.editor.json").exists())
            applied = apply_review_handoff(workspace, "story-1", 1, request, result)
            self.assertEqual(applied["status"], "applied")
            self.assertTrue((review_root / "standard.editor.normalization.json").exists())
            reapplied = apply_review_handoff(workspace, "story-1", 1, request, result)
            self.assertEqual(reapplied["status"], "already_applied")

    def test_execute_rejects_a_stale_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            request = prepare_review_handoff(workspace, "story-1", 1)
            draft = workspace / "fixture_stories" / "story-1" / "drafts" / "chapter_001.md"
            draft.write_text(draft.read_text(encoding="utf-8") + "\nChanged.", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "stale"):
                execute_review_handoff(workspace, "story-1", 1, request, str(FIXTURES / "mock_config.yaml"))

    def test_apply_rejects_tampered_or_partial_result_without_current_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            request = prepare_review_handoff(workspace, "story-1", 1)
            result = execute_review_handoff(workspace, "story-1", 1, request, str(FIXTURES / "mock_config.yaml"))
            manifest = json.loads(result.read_text(encoding="utf-8"))
            record_path = workspace / "fixture_stories" / "story-1" / manifest["records"][0]["record"]
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["decision"]["summary"] = "Tampered after execution."
            record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            story = workspace / "fixture_stories" / "story-1"
            with self.assertRaisesRegex(RuntimeError, "tampered"):
                apply_review_handoff(workspace, "story-1", 1, request, result)
            self.assertFalse((story / "reviews" / "chapter" / "001" / "standard.editor.json").exists())

            record_path.unlink()
            with self.assertRaises(FileNotFoundError):
                apply_review_handoff(workspace, "story-1", 1, request, result)
            self.assertFalse((story / "reviews" / "chapter" / "001" / "standard.editor.json").exists())

    def test_apply_rejects_mixed_execution_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.copy_workspace(temp_dir)
            config = str(FIXTURES / "mock_config.yaml")
            request = prepare_review_handoff(workspace, "story-1", 1)
            first = execute_review_handoff(workspace, "story-1", 1, request, config)
            second = execute_review_handoff(workspace, "story-1", 1, request, config)
            first_manifest = json.loads(first.read_text(encoding="utf-8"))
            second_manifest = json.loads(second.read_text(encoding="utf-8"))
            first_record_path = first.parent / "records" / "standard.continuity.json"
            second_record_path = second.parent / "records" / "standard.continuity.json"
            first_record_path.write_bytes(second_record_path.read_bytes())
            relative = str(first_record_path.relative_to((workspace / "fixture_stories" / "story-1").resolve()))
            first_manifest["record_sha256"][relative] = hashlib.sha256(first_record_path.read_bytes()).hexdigest()
            unsigned = {key: value for key, value in first_manifest.items() if key != "result_digest"}
            first_manifest["result_digest"] = _digest(unsigned)
            first.write_text(json.dumps(first_manifest, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "mixes runs"):
                apply_review_handoff(workspace, "story-1", 1, request, first)


if __name__ == "__main__":
    unittest.main()
