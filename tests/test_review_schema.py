from __future__ import annotations

import copy
import json
import unittest

from shared.lib.review_parser import (
    parse_review_decision,
    parse_review_run_record,
    render_review_report,
    review_decision_gate,
    validate_review_decision,
    validate_review_run_record,
)


def valid_decision() -> dict[str, object]:
    return {
        "schema_version": 1,
        "reviewer_id": "style",
        "reviewer_type": "standard",
        "story_id": "story-1",
        "chapter": 7,
        "status": "pass",
        "summary": "The chapter advances through concrete action.",
        "evidence": [
            {
                "location": "opening scene",
                "observation": "The protagonist must answer an immediate demand.",
                "reader_effect": "The chapter begins with forward pressure.",
            }
        ],
        "severity_counts": {"blocker": 0, "major": 0, "minor": 0, "note": 0},
        "issues": [],
        "rewrite_recommendation": {"required": False, "scope": "none"},
        "gate_recommendation": "accept",
        "carry_forward_tasks": [],
        "reviewer_notes": [],
    }


def issue(
    issue_id: str = "R001",
    *,
    severity: str = "major",
    rewrite_required: bool = True,
    rewrite_scope: str = "scene",
) -> dict[str, object]:
    return {
        "issue_id": issue_id,
        "issue_type": "summary_instead_of_scene",
        "severity": severity,
        "location": "middle scene",
        "observation": "The conflict is summarized after it has already happened.",
        "reader_effect": "The central turn feels remote.",
        "review_scope": "scene",
        "rewrite_required": rewrite_required,
        "rewrite_scope": rewrite_scope,
        "suggested_fix": "Dramatize the refusal and its immediate consequence.",
    }


def valid_run_record(
    decision: dict[str, object] | None = None,
    *,
    provider_type: str = "mock",
    session: dict[str, object] | None = None,
) -> dict[str, object]:
    decision = copy.deepcopy(decision or valid_decision())
    codex = provider_type == "codex_cli"
    return {
        "schema_version": 1,
        "run_id": "20260717T120000Z-style",
        "recorded_at": "2026-07-17T12:00:00Z",
        "draft_sha256": "a" * 64,
        "reviewer": {"id": decision["reviewer_id"], "type": decision["reviewer_type"]},
        "provider": {
            "id": "codex-review" if codex else "mock-local",
            "type": provider_type,
            "model_profile": "codex_reviewer" if codex else "mock_reviewer",
            "codex_profile": "twr-reviewer" if codex else None,
            "model": "gpt-5.5" if codex else None,
            "reasoning_effort": "high" if codex else None,
            "requested_intelligence": "high" if codex else None,
            "resolved_intelligence": "high" if codex else None,
        },
        "session": session,
        "usage": {"input_tokens": 1200, "output_tokens": 300},
        "outputs": {
            "decision_json": "reviews/chapter/007/current/style.json",
            "report_markdown": "reviews/chapter/007/current/style.md",
        },
        "decision": decision,
    }


class ReviewDecisionSchemaTests(unittest.TestCase):
    def test_valid_decision_parses_and_renders_canonical_markdown(self) -> None:
        decision = valid_decision()

        parsed = parse_review_decision(
            json.dumps(decision),
            reviewer_id="style",
            reviewer_type="standard",
            story_id="story-1",
            chapter=7,
        )
        report = render_review_report(
            parsed,
            valid_run_record(
                provider_type="codex_cli",
                session={
                    "start_mode": "fresh",
                    "retention": "persisted",
                    "thread_id": "thread-123",
                    "resumed_from": None,
                },
            ),
        )

        self.assertEqual(parsed, decision)
        self.assertEqual(review_decision_gate(parsed, can_block=True), "accepted")
        self.assertIn("reviewer_id: style", report)
        self.assertIn("- Codex Profile: twr-reviewer", report)
        self.assertIn("- Session Retention: persisted", report)
        self.assertIn("- Thread ID: thread-123", report)
        self.assertTrue(report.endswith("\n"))

    def test_schema_rejects_unknown_fields_and_identity_mismatch(self) -> None:
        decision = valid_decision()
        decision["unexpected"] = True
        errors = validate_review_decision(decision)

        self.assertTrue(any("Additional properties are not allowed" in error for error in errors))

        with self.assertRaisesRegex(ValueError, "reviewer_id must be continuity"):
            parse_review_decision(
                json.dumps(valid_decision()),
                reviewer_id="continuity",
                reviewer_type="standard",
                story_id="story-1",
                chapter=7,
            )

    def test_semantic_validation_enforces_counts_unique_ids_and_rewrite_scope(self) -> None:
        decision = valid_decision()
        decision.update(
            {
                "status": "needs_revision",
                "issues": [issue(), issue("R001", rewrite_scope="chapter")],
                "severity_counts": {"blocker": 0, "major": 1, "minor": 0, "note": 0},
                "rewrite_recommendation": {"required": True, "scope": "paragraph"},
                "gate_recommendation": "revise",
            }
        )

        errors = validate_review_decision(decision)

        self.assertIn("issue_id values must be unique", errors)
        self.assertIn("severity_counts must exactly match issues", errors)
        self.assertIn("rewrite_recommendation.scope cannot be narrower than an issue rewrite_scope", errors)

    def test_pass_status_cannot_hide_major_issue_or_required_rewrite(self) -> None:
        decision = valid_decision()
        decision["issues"] = [issue()]
        decision["severity_counts"] = {"blocker": 0, "major": 1, "minor": 0, "note": 0}
        decision["rewrite_recommendation"] = {"required": True, "scope": "scene"}

        errors = validate_review_decision(decision)

        self.assertIn("status pass cannot include blocker or major issues", errors)
        self.assertIn("status pass cannot require rewriting", errors)


class ReviewRunRecordSchemaTests(unittest.TestCase):
    def test_stateless_provider_record_is_valid_and_round_trips(self) -> None:
        record = valid_run_record()

        self.assertEqual(validate_review_run_record(record), [])
        self.assertEqual(parse_review_run_record(json.dumps(record)), record)

    def test_codex_record_accepts_fresh_persisted_and_ephemeral_sessions(self) -> None:
        for retention in ("persisted", "ephemeral"):
            with self.subTest(retention=retention):
                record = valid_run_record(
                    provider_type="codex_cli",
                    session={
                        "start_mode": "fresh",
                        "retention": retention,
                        "thread_id": f"thread-{retention}",
                        "resumed_from": None,
                    },
                )

                self.assertEqual(validate_review_run_record(record), [])

    def test_codex_record_rejects_resumed_or_unidentified_session(self) -> None:
        record = valid_run_record(
            provider_type="codex_cli",
            session={
                "start_mode": "resumed",
                "retention": "persisted",
                "thread_id": None,
                "resumed_from": "older-thread",
            },
        )

        errors = validate_review_run_record(record)

        self.assertIn("codex_cli review must start a fresh session", errors)
        self.assertIn("codex_cli review requires a thread_id", errors)
        self.assertIn("fresh codex_cli review cannot resume another session", errors)

    def test_non_threaded_provider_rejects_session_metadata(self) -> None:
        record = valid_run_record(
            session={
                "start_mode": "fresh",
                "retention": "ephemeral",
                "thread_id": "thread-123",
                "resumed_from": None,
            }
        )

        self.assertIn("non-threaded review providers must use session null", validate_review_run_record(record))

    def test_record_requires_valid_timestamp_and_matching_reviewer(self) -> None:
        record = valid_run_record()
        record["recorded_at"] = "yesterday"
        record["reviewer"] = {"id": "continuity", "type": "standard"}

        errors = validate_review_run_record(record)

        self.assertIn("recorded_at must be an RFC 3339 date-time", errors)
        self.assertIn("reviewer_id must be continuity", errors)

        record = valid_run_record()
        record["recorded_at"] = "2026-07-17 12:00:00+00:00"
        self.assertIn(
            "recorded_at must be an RFC 3339 date-time",
            validate_review_run_record(record),
        )


if __name__ == "__main__":
    unittest.main()
