from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared.lib.codex_cli_runner import (
    build_codex_command,
    parse_codex_jsonl,
    run_codex_cli_model,
    validate_codex_profile,
    validate_codex_runtime,
)
from shared.lib.review_parser import REVIEW_DECISION_SCHEMA_PATH


VALID_PROFILE = '''approval_policy = "never"
sandbox_mode = "read-only"
web_search = "disabled"
developer_instructions = "Review only the supplied packet and return the requested schema."

[shell_environment_policy]
inherit = "none"

[features]
apps = false
goals = false
hooks = false
memories = false
multi_agent = false
shell_tool = false
'''


def provider(
    retention: str = "persisted",
    codex_home: str = "~/.codex/twr-reviewer",
) -> dict[str, object]:
    return {
        "enabled": True,
        "type": "codex_cli",
        "command": "codex",
        "profile": "twr-reviewer",
        "codex_home": codex_home,
        "timeout_seconds": 30,
        "session": {"start_mode": "fresh", "retention": retention},
    }


def model_profile() -> dict[str, str]:
    return {
        "model": "gpt-5.5",
        "reasoning_effort": "high",
        "requested_intelligence": "high",
        "resolved_intelligence": "high",
    }


def success_jsonl() -> str:
    return "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "thread-123"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": '{"schema_version":1}'},
                }
            ),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 100, "output_tokens": 20, "ignored": "value"},
                }
            ),
        ]
    )


class CodexCliRunnerTests(unittest.TestCase):
    def write_profile(self, root: str, contents: str = VALID_PROFILE) -> Path:
        path = Path(root) / "twr-reviewer.config.toml"
        path.write_text(contents, encoding="utf-8")
        return path

    def test_profile_validation_enforces_dedicated_isolation_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"CODEX_HOME": temp_dir}
        ):
            self.assertTrue(validate_codex_profile("twr-reviewer"))

            self.write_profile(temp_dir, 'approval_policy = "on-request"\n')
            errors = validate_codex_profile("twr-reviewer")

            self.assertTrue(any("approval_policy" in error for error in errors))
            self.assertTrue(any("sandbox_mode" in error for error in errors))
            self.assertTrue(any("web_search" in error for error in errors))
            self.assertTrue(any("developer_instructions" in error for error in errors))
            self.assertTrue(any("shell_environment_policy" in error for error in errors))
            self.assertTrue(any("features.shell_tool" in error for error in errors))

            self.write_profile(temp_dir)
            self.assertEqual(validate_codex_profile("twr-reviewer"), [])

            (Path(temp_dir) / "AGENTS.md").write_text("Personal instructions.\n", encoding="utf-8")
            errors = validate_codex_profile("twr-reviewer")
            self.assertTrue(any("must not contain instruction file" in error for error in errors))

    def test_command_maps_model_reasoning_profile_and_session_retention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            persisted = build_codex_command(
                provider("persisted"),
                model_profile(),
                REVIEW_DECISION_SCHEMA_PATH,
                temp_dir,
            )
            ephemeral = build_codex_command(
                provider("ephemeral"),
                model_profile(),
                REVIEW_DECISION_SCHEMA_PATH,
                temp_dir,
            )

        self.assertEqual(persisted[:4], ["codex", "exec", "--profile", "twr-reviewer"])
        self.assertIn("--ignore-user-config", persisted)
        self.assertIn("--ignore-rules", persisted)
        self.assertIn("--strict-config", persisted)
        self.assertIn("read-only", persisted)
        self.assertEqual(persisted[persisted.index("--model") + 1], "gpt-5.5")
        self.assertIn('model_reasoning_effort="high"', persisted)
        self.assertEqual(persisted[-1], "-")
        self.assertNotIn("--ephemeral", persisted)
        self.assertIn("--ephemeral", ephemeral)
        self.assertNotIn("resume", persisted)
        self.assertNotIn("resume", ephemeral)

    def test_command_rejects_resumed_sessions_and_invalid_reasoning(self) -> None:
        resumed = provider()
        resumed["session"] = {"start_mode": "resumed", "retention": "persisted"}
        with self.assertRaisesRegex(ValueError, "only supports session.start_mode fresh"):
            build_codex_command(resumed, model_profile(), REVIEW_DECISION_SCHEMA_PATH, ".")

        invalid_model = model_profile()
        invalid_model["reasoning_effort"] = "extreme"
        with self.assertRaisesRegex(ValueError, "reasoning_effort is invalid"):
            build_codex_command(provider(), invalid_model, REVIEW_DECISION_SCHEMA_PATH, ".")

    def test_jsonl_parser_extracts_fresh_thread_final_message_and_usage(self) -> None:
        parsed = parse_codex_jsonl(success_jsonl())

        self.assertEqual(parsed["thread_id"], "thread-123")
        self.assertEqual(parsed["text"], '{"schema_version":1}')
        self.assertEqual(parsed["usage"], {"input_tokens": 100, "output_tokens": 20})

    def test_jsonl_parser_fails_closed_on_malformed_failed_or_incomplete_stream(self) -> None:
        cases = {
            "malformed": ("not-json", "invalid Codex JSONL"),
            "failed": (
                json.dumps({"type": "error", "message": "provider unavailable"}),
                "Codex run failed: provider unavailable",
            ),
            "missing thread": (
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "answer"},
                    }
                ),
                "did not contain thread.started",
            ),
            "missing answer": (
                json.dumps({"type": "thread.started", "thread_id": "thread-123"}),
                "did not contain a final agent message",
            ),
        }
        for name, (payload, message) in cases.items():
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                parse_codex_jsonl(payload)

    def test_runner_returns_concrete_model_and_fresh_session_provenance(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=success_jsonl(), stderr=""
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"CODEX_HOME": temp_dir}
        ), patch("shared.lib.codex_cli_runner.shutil.which", return_value="/usr/local/bin/codex"), patch(
            "shared.lib.codex_cli_runner.subprocess.run", return_value=completed
        ) as run:
            self.write_profile(temp_dir)

            result = run_codex_cli_model(
                provider("ephemeral", temp_dir),
                model_profile(),
                "Review this chapter.",
                {"output_schema_path": REVIEW_DECISION_SCHEMA_PATH},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["model"], "gpt-5.5")
        self.assertEqual(result["reasoning_effort"], "high")
        self.assertEqual(result["codex_profile"], "twr-reviewer")
        self.assertEqual(
            result["session"],
            {
                "start_mode": "fresh",
                "retention": "ephemeral",
                "thread_id": "thread-123",
                "resumed_from": None,
            },
        )
        self.assertEqual(result["usage"], {"input_tokens": 100, "output_tokens": 20})
        args, kwargs = run.call_args
        self.assertIn("--ephemeral", args[0])
        self.assertEqual(kwargs["input"], "Review this chapter.")
        self.assertTrue(kwargs["capture_output"])
        self.assertEqual(Path(kwargs["env"]["CODEX_HOME"]), Path(temp_dir).resolve())

    def test_runtime_validation_checks_login_without_running_a_review(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["codex", "login", "status"], returncode=0, stdout="Logged in", stderr=""
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"CODEX_HOME": temp_dir}
        ), patch("shared.lib.codex_cli_runner.shutil.which", return_value="/usr/local/bin/codex"), patch(
            "shared.lib.codex_cli_runner.subprocess.run", return_value=completed
        ) as run:
            self.write_profile(temp_dir)

            errors = validate_codex_runtime(provider(codex_home=temp_dir))

        self.assertEqual(errors, [])
        self.assertEqual(run.call_args.args[0], ["codex", "login", "status"])
        self.assertEqual(
            Path(run.call_args.kwargs["env"]["CODEX_HOME"]),
            Path(temp_dir).resolve(),
        )


if __name__ == "__main__":
    unittest.main()
