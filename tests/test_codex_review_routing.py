from __future__ import annotations

import copy
import unittest

from shared.lib.config_loader import load_config_example, validate_config
from shared.lib.model_router import select_model_for_reviewer


class CodexReviewRoutingTests(unittest.TestCase):
    def test_intelligence_resolves_to_concrete_codex_model_and_reasoning(self) -> None:
        config = load_config_example()

        chain = select_model_for_reviewer(
            config,
            {"provider_group": "codex_review", "intelligence": "very_high"},
        )

        self.assertEqual(len(chain), 1)
        self.assertEqual(chain[0]["model"], "gpt-5.5")
        self.assertEqual(chain[0]["reasoning_effort"], "xhigh")
        self.assertEqual(chain[0]["requested_intelligence"], "very_high")
        self.assertEqual(chain[0]["resolved_intelligence"], "very_high")

    def test_codex_provider_requires_a_complete_intelligence_map(self) -> None:
        config = copy.deepcopy(load_config_example())
        del config["review_policy"]["codex_intelligence_map"]["high"]

        errors = validate_config(config)

        self.assertIn("Codex intelligence mapping is missing: high", errors)
        with self.assertRaisesRegex(ValueError, "mapping is missing: high"):
            select_model_for_reviewer(
                config,
                {"provider_group": "codex_review", "intelligence": "high"},
            )

        config = copy.deepcopy(load_config_example())
        config["review_policy"]["codex_intelligence_map"]["high"]["reasoning_effort"] = "extreme"
        with self.assertRaisesRegex(ValueError, "mapping is invalid: high"):
            select_model_for_reviewer(
                config,
                {"provider_group": "codex_review", "intelligence": "high"},
            )

    def test_codex_provider_requires_a_dedicated_home(self) -> None:
        config = copy.deepcopy(load_config_example())
        del config["providers"]["codex"]["codex_home"]

        self.assertIn(
            "Codex provider codex requires a dedicated codex_home",
            validate_config(config),
        )


if __name__ == "__main__":
    unittest.main()
