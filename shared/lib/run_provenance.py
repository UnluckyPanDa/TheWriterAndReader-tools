"""Fail-closed runtime configuration checks and model-run provenance records."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

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
    details: dict[str, Any] | None = None,
) -> Path:
    """Persist latest and immutable run records without storing prompts."""
    root = Path(story_path).expanduser().resolve(strict=False)
    payload = build_run_provenance_payload(chapter, operation, result, config, output_paths, details)
    return write_prepared_run_provenance(root, payload)


def build_run_provenance_payload(
    chapter: int,
    operation: str,
    result: dict[str, Any],
    config: dict[str, Any],
    output_paths: dict[str, str],
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare a provenance record without writing it."""
    details = details or {}
    run_id = str(details.get("run_id") or uuid4())
    payload = {
        "run_id": run_id,
        "operation": operation,
        "chapter": chapter,
        "recorded_at": datetime.now(UTC).isoformat(),
        "config_source": config.get("_source_path"),
        "model_profile": result.get("model_profile"),
        "attempts": result.get("attempts", []),
        "outputs": output_paths,
    }
    payload.update({key: value for key, value in details.items() if key != "run_id"})
    return payload


def write_prepared_run_provenance(story_path: str | Path, payload: dict[str, Any]) -> Path:
    """Persist a previously prepared provenance record."""
    root = Path(story_path).expanduser().resolve(strict=False)
    chapter = int(payload["chapter"])
    operation = str(payload["operation"])
    run_id = str(payload["run_id"])
    history_root = root / "runs" / f"chapter_{chapter:03d}" / run_id
    prepared_payload = dict(payload)
    attempts: list[Any] = []
    for index, source_attempt in enumerate(payload.get("attempts", []), start=1):
        if not isinstance(source_attempt, dict):
            attempts.append(source_attempt)
            continue
        attempt = dict(source_attempt)
        response_text = attempt.pop("response_text", None)
        if isinstance(response_text, str) and response_text:
            response_path = history_root / "responses" / f"attempt_{index:02d}.txt"
            assert_story_write_allowed(response_path, root)
            safe_write_file(response_path, response_text, root)
            attempt["response_artifact"] = str(response_path.relative_to(root))
            attempt["response_characters"] = len(response_text)
        attempts.append(attempt)
    prepared_payload["attempts"] = attempts
    history_path = history_root / f"{operation}.json"
    assert_story_write_allowed(history_path, root)
    serialized = json.dumps(prepared_payload, ensure_ascii=False, indent=2) + "\n"
    safe_write_file(history_path, serialized, root)
    output_path = root / "runs" / f"chapter_{chapter:03d}_{operation}.json"
    assert_story_write_allowed(output_path, root)
    return safe_write_file(output_path, serialized, root)
