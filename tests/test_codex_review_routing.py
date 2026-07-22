from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from shared.lib.config_loader import load_config_example, validate_config
from shared.lib.model_router import attempt_model_chain, select_model_for_reviewer, select_model_for_stage


class CodexReviewRoutingTests(unittest.TestCase):
    def test_example_config_has_complete_writer_and_reviewer_codex_contracts(self) -> None:
        self.assertEqual(validate_config(load_config_example()), [])

    def test_intelligence_resolves_to_concrete_codex_model_and_reasoning(self) -> None:
        config = load_config_example()

        for intelligence in ("low", "medium", "high", "very_high"):
            with self.subTest(intelligence=intelligence):
                chain = select_model_for_reviewer(
                    config,
                    {"provider_group": "codex_review", "intelligence": intelligence},
                )

                self.assertEqual(len(chain), 1)
                self.assertEqual(chain[0]["model"], "gpt-5.6-sol")
                self.assertEqual(chain[0]["reasoning_effort"], "high")
                self.assertEqual(chain[0]["requested_intelligence"], intelligence)
                self.assertEqual(chain[0]["resolved_intelligence"], intelligence)

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

    def test_writing_stage_resolves_to_the_dedicated_codex_writer(self) -> None:
        config = load_config_example()

        for intelligence in ("low", "medium", "high", "very_high"):
            with self.subTest(intelligence=intelligence):
                config["writing_stages"]["chapter_generation"]["intelligence"] = intelligence
                chain = select_model_for_stage(config, "chapter_generation")

                self.assertEqual(
                    [profile["profile_name"] for profile in chain],
                    ["local_writer", "codex_writer"],
                )
                self.assertEqual(chain[1]["model"], "gpt-5.6-terra")
                self.assertEqual(chain[1]["reasoning_effort"], "high")
                self.assertEqual(chain[1]["requested_intelligence"], intelligence)
                self.assertEqual(chain[1]["provider_config"]["capability"], "writing")

    def test_writing_codex_route_requires_its_own_intelligence_map(self) -> None:
        config = copy.deepcopy(load_config_example())
        del config["writing_policy"]["codex_intelligence_map"]["high"]

        self.assertIn("Codex writing intelligence mapping is missing: high", validate_config(config))
        with self.assertRaisesRegex(ValueError, "Codex writing intelligence mapping is missing: high"):
            select_model_for_stage(config, "chapter_generation")

    def test_writer_and_reviewer_codex_capabilities_cannot_cross_routes(self) -> None:
        config = copy.deepcopy(load_config_example())
        config["writing_stages"]["chapter_generation"]["provider_group"] = "codex_review"

        with self.assertRaisesRegex(ValueError, "review provider cannot serve writing routing"):
            select_model_for_stage(config, "chapter_generation")

        config = copy.deepcopy(load_config_example())
        config["fallback_chains"]["codex_review"] = ["codex_writer"]
        with self.assertRaisesRegex(ValueError, "writing provider cannot serve review routing"):
            select_model_for_reviewer(
                config,
                {"provider_group": "codex_review", "intelligence": "high"},
            )

    def test_custom_intelligence_remains_compatible_with_non_codex_routes(self) -> None:
        config = copy.deepcopy(load_config_example())
        config["writing_stages"]["chapter_generation"]["provider_group"] = "local_first"
        config["writing_stages"]["chapter_generation"]["intelligence"] = "custom-local"

        chain = select_model_for_stage(config, "chapter_generation")

        self.assertEqual([profile["profile_name"] for profile in chain], ["local_writer"])
        with self.assertRaisesRegex(ValueError, "Unknown writing intelligence: custom-local"):
            config["writing_stages"]["chapter_generation"][
                "provider_group"
            ] = "local_first_with_codex_fallback"
            select_model_for_stage(config, "chapter_generation")

    def test_failed_local_writer_falls_through_to_codex_writer(self) -> None:
        config = copy.deepcopy(load_config_example())
        config["providers"]["codex_writer"]["enabled"] = True
        chain = select_model_for_stage(config, "chapter_generation")

        with patch(
            "shared.lib.model_router.run_local_cli_model",
            return_value={"ok": False, "text": "", "reason": "local failed"},
        ) as local, patch(
            "shared.lib.model_router.run_codex_cli_model",
            return_value={
                "ok": True,
                "text": "Codex prose.",
                "reason": None,
                "model": "gpt-5.6-terra",
                "reasoning_effort": "high",
                "capability": "writing",
                "orchestration": "direct",
            },
        ) as codex:
            result = attempt_model_chain("Write the scene.", chain, config)

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "codex_writer")
        self.assertEqual(result["text"], "Codex prose.")
        local.assert_called_once()
        codex.assert_called_once()

    def test_structured_output_attempt_preserves_raw_provider_response(self) -> None:
        config = copy.deepcopy(load_config_example())
        config["writing_stages"]["chapter_generation"]["provider_group"] = "local_first"
        chain = select_model_for_stage(config, "chapter_generation")

        with patch(
            "shared.lib.model_router.run_local_cli_model",
            return_value={
                "ok": True,
                "text": '{"story_id":"story-1"}',
                "raw_response_text": '\n{"story_id":"story-1"}\n',
                "reason": None,
            },
        ):
            result = attempt_model_chain(
                "Return JSON.", chain, config, {"structured_output": True}
            )

        self.assertEqual(
            result["attempts"][0]["response_text"],
            '\n{"story_id":"story-1"}\n',
        )


if __name__ == "__main__":
    unittest.main()
