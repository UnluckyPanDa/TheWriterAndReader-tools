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
plugins = false
shell_tool = false
'''

SUBAGENT_PROFILE = VALID_PROFILE.replace(
    """multi_agent = false
plugins = false
shell_tool = false""",
    """multi_agent = true
plugins = false
shell_tool = false

[agents]
max_threads = 2
max_depth = 1
interrupt_message = false""",
)

VALID_AGENT = '''name = "twr_story_reviewer"
description = "Independent fiction review evidence pass."
approval_policy = "never"
sandbox_mode = "read-only"
web_search = "disabled"
developer_instructions = "Review only the supplied assignment."

[shell_environment_policy]
inherit = "none"

[features]
apps = false
goals = false
hooks = false
memories = false
multi_agent = false
plugins = false
shell_tool = false
'''


def provider(
    retention: str = "persisted",
    codex_home: str = "~/.codex/twr-reviewer",
    *,
    capability: str = "review",
    subagents: bool = False,
) -> dict[str, object]:
    result: dict[str, object] = {
        "enabled": True,
        "type": "codex_cli",
        "capability": capability,
        "command": "codex",
        "profile": "twr-reviewer" if capability == "review" else "twr-writer",
        "codex_home": codex_home,
        "timeout_seconds": 30,
        "session": {"start_mode": "fresh", "retention": retention},
    }
    if subagents:
        result["subagents"] = {
            "required": True,
            "count": 1,
            "agent": "twr_story_reviewer",
        }
    return result


def model_profile(model: str = "gpt-5.6-sol") -> dict[str, str]:
    return {
        "model": model,
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


def delegated_jsonl(*, final_before_wait: bool = False) -> str:
    final = json.dumps(
        {
            "type": "item.completed",
            "item": {"id": "answer", "type": "agent_message", "text": '{"schema_version":1}'},
        }
    )
    wait = json.dumps(
        {
            "type": "item.completed",
            "item": {
                "id": "wait-1",
                "type": "collab_tool_call",
                "tool": "wait",
                "sender_thread_id": "thread-123",
                "receiver_thread_ids": ["child-456"],
                "prompt": None,
                "agents_states": {
                    "child-456": {"status": "completed", "message": "Evidence complete."}
                },
                "status": "completed",
            },
        }
    )
    events = [
        json.dumps({"type": "thread.started", "thread_id": "thread-123"}),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "spawn-1",
                    "type": "collab_tool_call",
                    "tool": "spawn_agent",
                    "sender_thread_id": "thread-123",
                    "receiver_thread_ids": ["child-456"],
                    "prompt": "Review the complete assignment.",
                    "agents_states": {},
                    "status": "completed",
                },
            }
        ),
        final if final_before_wait else wait,
        wait if final_before_wait else final,
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 100, "output_tokens": 20},
            }
        ),
    ]
    return "\n".join(events)


class CodexCliRunnerTests(unittest.TestCase):
    def write_profile(
        self,
        root: str,
        contents: str = VALID_PROFILE,
        name: str = "twr-reviewer",
    ) -> Path:
        path = Path(root) / f"{name}.config.toml"
        path.write_text(contents, encoding="utf-8")
        return path

    def write_agent(self, root: str, contents: str = VALID_AGENT) -> Path:
        path = Path(root) / "agents" / "twr_story_reviewer.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
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
            self.assertTrue(any("features.plugins" in error for error in errors))
            self.assertTrue(any("features.shell_tool" in error for error in errors))

            self.write_profile(temp_dir)
            self.assertEqual(validate_codex_profile("twr-reviewer"), [])

            (Path(temp_dir) / "AGENTS.md").write_text("Personal instructions.\n", encoding="utf-8")
            errors = validate_codex_profile("twr-reviewer")
            self.assertTrue(any("must not contain instruction file" in error for error in errors))

    def test_profiles_enforce_writer_direct_and_reviewer_subagent_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_profile(temp_dir, VALID_PROFILE, "twr-writer")
            writer = provider(codex_home=temp_dir, capability="writing")
            self.assertEqual(validate_codex_profile("twr-writer", temp_dir, writer), [])

            reviewer = provider(codex_home=temp_dir, subagents=True)
            self.write_profile(temp_dir, SUBAGENT_PROFILE)
            errors = validate_codex_profile("twr-reviewer", temp_dir, reviewer)
            self.assertTrue(any("subagent profile is missing" in error for error in errors))

            self.write_agent(temp_dir)
            self.assertEqual(validate_codex_profile("twr-reviewer", temp_dir, reviewer), [])

            self.write_profile(temp_dir, VALID_PROFILE)
            errors = validate_codex_profile("twr-reviewer", temp_dir, reviewer)
            self.assertTrue(any("features.multi_agent = true" in error for error in errors))

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
        self.assertEqual(persisted[persisted.index("--model") + 1], "gpt-5.6-sol")
        self.assertIn('model_reasoning_effort="high"', persisted)
        self.assertEqual(persisted[-1], "-")
        self.assertNotIn("--ephemeral", persisted)
        self.assertIn("--ephemeral", ephemeral)
        self.assertNotIn("resume", persisted)
        self.assertNotIn("resume", ephemeral)

        writer = build_codex_command(
            provider("ephemeral", capability="writing"),
            model_profile("gpt-5.6-terra"),
            None,
            ".",
        )
        self.assertNotIn("--output-schema", writer)
        self.assertEqual(writer[writer.index("--profile") + 1], "twr-writer")

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
        self.assertIsNone(parsed["delegation"])

    def test_jsonl_parser_verifies_completed_subagent_before_final_response(self) -> None:
        parsed = parse_codex_jsonl(delegated_jsonl(), require_delegation=True)

        self.assertEqual(
            parsed["delegation"],
            {
                "mode": "codex_native",
                "required": True,
                "spawned_thread_ids": ["child-456"],
                "completed_thread_ids": ["child-456"],
            },
        )

    def test_jsonl_parser_fails_closed_when_required_delegation_is_incomplete(self) -> None:
        missing_spawn = "\n".join(delegated_jsonl().splitlines()[0:1] + delegated_jsonl().splitlines()[2:])
        missing_wait = "\n".join(delegated_jsonl().splitlines()[0:2] + delegated_jsonl().splitlines()[3:])
        errored_child = delegated_jsonl().replace(
            '"status": "completed", "message": "Evidence complete."',
            '"status": "errored", "message": "Review failed."',
        )
        duplicate_child = delegated_jsonl().replace(
            '"receiver_thread_ids": ["child-456"], "prompt": "Review the complete assignment."',
            '"receiver_thread_ids": ["child-456", "child-789"], "prompt": "Review the complete assignment."',
        )
        wrong_sender = delegated_jsonl().replace(
            '"sender_thread_id": "thread-123"',
            '"sender_thread_id": "another-thread"',
            1,
        )
        empty_result = delegated_jsonl().replace(
            '"message": "Evidence complete."',
            '"message": ""',
        )
        empty_prompt = delegated_jsonl().replace(
            '"prompt": "Review the complete assignment."',
            '"prompt": ""',
        )
        cases = {
            "missing spawn": (missing_spawn, "exactly one completed subagent spawn"),
            "missing wait": (missing_wait, "did not complete through a later wait"),
            "errored child": (errored_child, "did not complete through a later wait"),
            "duplicate child": (duplicate_child, "exactly one completed subagent spawn"),
            "wrong sender": (wrong_sender, "exactly one completed subagent spawn"),
            "empty prompt": (empty_prompt, "exactly one completed subagent spawn"),
            "empty result": (empty_result, "did not complete through a later wait"),
            "premature final": (delegated_jsonl(final_before_wait=True), "preceded subagent completion"),
        }
        for name, (payload, message) in cases.items():
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                parse_codex_jsonl(payload, require_delegation=True)

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
        self.assertEqual(result["model"], "gpt-5.6-sol")
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

    def test_runner_supports_plain_writer_output_without_a_schema(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=success_jsonl(), stderr=""
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "shared.lib.codex_cli_runner.shutil.which", return_value="/usr/local/bin/codex"
        ), patch("shared.lib.codex_cli_runner.subprocess.run", return_value=completed) as run:
            self.write_profile(temp_dir, VALID_PROFILE, "twr-writer")
            result = run_codex_cli_model(
                provider("ephemeral", temp_dir, capability="writing"),
                model_profile("gpt-5.6-terra"),
                "Write this scene.",
                {"output_schema_path": REVIEW_DECISION_SCHEMA_PATH},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["capability"], "writing")
        self.assertEqual(result["orchestration"], "direct")
        self.assertNotIn("--output-schema", run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["input"], "Write this scene.")

    def test_runner_uses_a_writer_schema_only_for_explicit_structured_output(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=success_jsonl(), stderr=""
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "shared.lib.codex_cli_runner.shutil.which", return_value="/usr/local/bin/codex"
        ), patch("shared.lib.codex_cli_runner.subprocess.run", return_value=completed) as run:
            self.write_profile(temp_dir, VALID_PROFILE, "twr-writer")
            result = run_codex_cli_model(
                provider("ephemeral", temp_dir, capability="writing"),
                model_profile("gpt-5.6-terra"),
                "Plan this scene.",
                {
                    "structured_output": True,
                    "output_schema_path": REVIEW_DECISION_SCHEMA_PATH,
                },
            )

        self.assertTrue(result["ok"])
        self.assertIn("--output-schema", run.call_args.args[0])

    def test_runner_requires_and_records_one_reviewer_subagent(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=delegated_jsonl(), stderr=""
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "shared.lib.codex_cli_runner.shutil.which", return_value="/usr/local/bin/codex"
        ), patch("shared.lib.codex_cli_runner.subprocess.run", return_value=completed) as run:
            self.write_profile(temp_dir, SUBAGENT_PROFILE)
            self.write_agent(temp_dir)
            result = run_codex_cli_model(
                provider("persisted", temp_dir, subagents=True),
                model_profile(),
                "Review this chapter.",
                {"output_schema_path": REVIEW_DECISION_SCHEMA_PATH},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["orchestration"], "codex_subagent")
        self.assertEqual(
            result["session"]["delegation"]["completed_thread_ids"],
            ["child-456"],
        )
        self.assertIn("exactly one Codex subagent", run.call_args.kwargs["input"])
        self.assertIn("Review this chapter.", run.call_args.kwargs["input"])

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
