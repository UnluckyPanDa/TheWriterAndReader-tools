"""Fail-closed runtime configuration checks and model-run provenance records."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.safe_write import safe_write_file


def require_explicit_runtime_config(config: dict[str, Any], operation: str) -> None:
    """Reject example configuration for model-backed story operations."""
    if config.get("_used_example_config"):
        missing = config.get("_missing_external_config", "the configured path")
        raise RuntimeError(
            f"{operation} requires an explicit runtime config; {missing} is missing. "
            "Pass --config with a real local-model configuration."
        )


def write_run_provenance(
    story_path: str | Path,
    chapter: int,
    operation: str,
    result: dict[str, Any],
    config: dict[str, Any],
    output_paths: dict[str, str],
) -> Path:
    """Persist the selected model and fallback attempts without storing prompts."""
    root = Path(story_path).expanduser().resolve(strict=False)
    payload = {
        "operation": operation,
        "chapter": chapter,
        "recorded_at": datetime.now(UTC).isoformat(),
        "config_source": config.get("_source_path"),
        "model_profile": result.get("model_profile"),
        "attempts": result.get("attempts", []),
        "outputs": output_paths,
    }
    output_path = root / "runs" / f"chapter_{chapter:03d}_{operation}.json"
    assert_story_write_allowed(output_path, root)
    return safe_write_file(output_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n", root)
