from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from cli.commands.doctor import main


class CodexDoctorTest(unittest.TestCase):
    def run_doctor(self, config: dict[str, object]) -> tuple[int, str]:
        output = io.StringIO()
        with (
            patch("shared.lib.config_loader.load_config", return_value=config),
            patch("shared.lib.config_loader.validate_config", return_value=[]),
            patch("shared.lib.path_rules.assert_tools_repo_has_no_story_content", return_value=[]),
            redirect_stdout(output),
        ):
            result = main([])
        return result, output.getvalue()

    def test_enabled_codex_provider_runs_runtime_validation(self) -> None:
        provider = {
            "type": "codex_cli",
            "enabled": True,
            "command": "codex",
            "profile": "twr-reviewer",
        }
        config = {"providers": {"codex_review": provider}}

        with patch(
            "shared.lib.codex_cli_runner.validate_codex_runtime",
            return_value=["Codex authentication is unavailable: not logged in"],
        ) as validate_runtime:
            result, output = self.run_doctor(config)

        self.assertEqual(result, 1)
        validate_runtime.assert_called_once_with(provider)
        self.assertIn(
            "error: provider codex_review: Codex authentication is unavailable: not logged in",
            output,
        )

    def test_disabled_codex_provider_skips_runtime_validation(self) -> None:
        config = {
            "providers": {
                "codex_review": {
                    "type": "codex_cli",
                    "enabled": False,
                    "command": "codex",
                    "profile": "twr-reviewer",
                }
            }
        }

        with patch("shared.lib.codex_cli_runner.validate_codex_runtime") as validate_runtime:
            result, output = self.run_doctor(config)

        self.assertEqual(result, 0)
        validate_runtime.assert_not_called()
        self.assertEqual(output, "doctor ok\n")

    def test_runtime_issues_are_aggregated_for_each_enabled_provider(self) -> None:
        first = {"type": "codex_cli", "enabled": True}
        second = {"type": "codex_cli", "enabled": True}
        config = {"providers": {"first": first, "second": second}}

        with patch(
            "shared.lib.codex_cli_runner.validate_codex_runtime",
            side_effect=[["first issue"], ["second issue"]],
        ) as validate_runtime:
            result, output = self.run_doctor(config)

        self.assertEqual(result, 1)
        self.assertEqual(validate_runtime.call_count, 2)
        self.assertIn("error: provider first: first issue", output)
        self.assertIn("error: provider second: second issue", output)


if __name__ == "__main__":
    unittest.main()
