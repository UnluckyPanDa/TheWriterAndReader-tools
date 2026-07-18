from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.commands.setup import ensure_setup
from shared.lib.config_loader import load_yaml


class SetupTests(unittest.TestCase):
    def test_first_run_creates_config_and_selects_reachable_local_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.yaml"
            with patch(
                "cli.commands.setup._discover_ollama_models",
                return_value=["another:latest", "qwen3.5:latest"],
            ):
                result, created = ensure_setup(str(path))

            self.assertTrue(created)
            self.assertEqual(result, path)
            self.assertEqual(
                load_yaml(path)["model_profiles"]["local_writer"]["model"],
                "qwen3.5:latest",
            )

    def test_existing_config_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.yaml"
            path.write_text("custom: true\n", encoding="utf-8")

            result, created = ensure_setup(str(path))

            self.assertFalse(created)
            self.assertEqual(result, path)
            self.assertEqual(path.read_text(encoding="utf-8"), "custom: true\n")


if __name__ == "__main__":
    unittest.main()
