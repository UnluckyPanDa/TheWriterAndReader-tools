from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from cli.twr import main as cli_main
from shared.lib.local_cli_runner import run_local_cli_model
from shared.lib.model_router import attempt_model_chain, attempt_structured_model_chain


class LocalOllamaTransportTests(unittest.TestCase):
    def test_structured_request_uses_exact_schema_and_suppresses_thinking(self) -> None:
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = Path(temp_dir) / "schema.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {"response": '{"ok":true}', "thinking": "hidden trace"}
            with patch("shared.lib.local_cli_runner.requests.post", return_value=response) as post:
                result = run_local_cli_model(
                    {"command": "ollama", "enabled": True},
                    {"model": "qwen3.5:latest"},
                    "Return JSON.",
                    {"structured_output": True, "output_schema_path": str(schema_path)},
                )

        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], '{"ok":true}')
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["format"], schema)
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertNotIn("thinking", result["text"])

    def test_prose_request_omits_format(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "Clean prose."}
        with patch("shared.lib.local_cli_runner.requests.post", return_value=response) as post:
            result = run_local_cli_model(
                {"command": "/usr/local/bin/ollama", "enabled": True},
                {"model": "qwen3.5:latest"},
                "Write prose.",
            )
        self.assertTrue(result["ok"])
        self.assertNotIn("format", post.call_args.kwargs["json"])


class StructuredFallbackTests(unittest.TestCase):
    def test_model_chain_reports_progress_without_changing_result(self) -> None:
        messages: list[str] = []
        profile = {
            "profile_name": "mock_writer",
            "provider": "mock",
            "provider_config": {"type": "mock", "enabled": True},
            "model": "mock-writer",
        }

        result = attempt_model_chain(
            "Write prose.",
            [profile],
            {"allow_mock": True},
            {"progress_callback": messages.append, "progress_label": "scene draft scene-1"},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            messages,
            [
                "scene draft scene-1: trying mock_writer",
                "scene draft scene-1: mock_writer completed",
            ],
        )

    def test_each_model_gets_one_repair_before_fallback(self) -> None:
        provider = {"type": "local_cli", "enabled": True, "command": "ollama"}
        chain = [
            {"profile_name": "first", "provider": "ollama", "provider_config": provider, "model": "first"},
            {"profile_name": "second", "provider": "ollama", "provider_config": provider, "model": "second"},
        ]
        responses = [
            {"ok": True, "text": "bad", "reason": None},
            {"ok": True, "text": "still bad", "reason": None},
            {"ok": True, "text": '{"valid": true}', "reason": None},
        ]

        def validate(text: str) -> dict[str, object]:
            data = json.loads(text)
            if data != {"valid": True}:
                raise ValueError("wrong value")
            return data

        with patch("shared.lib.model_router.run_local_cli_model", side_effect=responses) as runner:
            result = attempt_structured_model_chain(
                "initial",
                chain,
                {},
                validate,
                lambda text, error: f"repair {error}: {text}",
                {"output_schema_path": "/tmp/schema.json"},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["model_profile"], "second")
        self.assertEqual([item["phase"] for item in result["attempts"]], ["initial", "repair", "initial"])
        self.assertEqual([item["status"] for item in result["attempts"]], ["invalid", "invalid", "success"])
        self.assertEqual(runner.call_count, 3)


class WritingCliProgressTests(unittest.TestCase):
    def test_draft_progress_uses_stderr_and_keeps_path_on_stdout(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        def fake_generate(*args: object) -> Path:
            options = args[4]
            options["progress_callback"]("scene contract: trying local_writer")
            return Path("/tmp/chapter_001.md")

        with (
            patch("tools.writing.generate_draft.generate_draft", side_effect=fake_generate),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            result = cli_main(
                [
                    "write",
                    "draft",
                    "--workspace",
                    "/tmp/workspace",
                    "--story",
                    "story-1",
                    "--chapter",
                    "1",
                ]
            )

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), "/tmp/chapter_001.md\n")
        self.assertEqual(stderr.getvalue(), "[twr] scene contract: trying local_writer\n")


if __name__ == "__main__":
    unittest.main()
