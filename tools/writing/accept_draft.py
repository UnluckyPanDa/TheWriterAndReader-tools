"""Promote a gate-approved draft and derive accepted chapter state."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from shared.lib.acceptance_contract import (
    ACCEPTANCE_GROUNDING_SCHEMA_PATH,
    ACCEPTED_CONTINUITY_SCHEMA_PATH,
    parse_acceptance_grounding,
    parse_accepted_continuity,
    render_accepted_continuity,
)
from shared.lib.config_loader import load_config
from shared.lib.model_router import attempt_structured_model_chain, select_model_for_stage
from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.review_parser import parse_review_run_record
from shared.lib.revision_evidence import revision_resolution_status
from shared.lib.run_provenance import (
    build_run_provenance_payload,
    require_explicit_runtime_config,
    write_prepared_run_provenance,
    write_run_provenance,
)
from shared.lib.safe_write import safe_write_file
from shared.lib.workspace_loader import resolve_story_path
from shared.lib.yaml_utils import dump_yaml, load_yaml_text


REQUIRED_ACCEPTANCE_REVIEWERS = (
    "continuity",
    "reveal_lock",
    "editor",
    "pacing",
    "tone",
    "character",
)


def _gate_field(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*([^\n]+)$", text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip().lower() if match else ""


def _validate_review_evidence(
    story_path: Path,
    story_id: str,
    chapter: int,
    draft_sha256: str,
) -> None:
    review_root = story_path / "reviews" / "chapter" / f"{chapter:03d}"
    for reviewer_id in REQUIRED_ACCEPTANCE_REVIEWERS:
        record_path = review_root / f"standard.{reviewer_id}.json"
        if not record_path.exists():
            raise RuntimeError(f"current canonical review record is missing: standard.{reviewer_id}")
        try:
            record = parse_review_run_record(record_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise RuntimeError(f"current canonical review record is invalid: standard.{reviewer_id}: {exc}") from exc
        decision = record["decision"]
        if (
            record["draft_sha256"] != draft_sha256
            or record["reviewer"] != {"id": reviewer_id, "type": "standard"}
            or decision["story_id"] != story_id
            or decision["chapter"] != chapter
        ):
            raise RuntimeError(f"current canonical review record does not match the draft: standard.{reviewer_id}")


def _validate_gate(story_path: Path, story_id: str, chapter: int, draft: str) -> Path:
    gate_path = story_path / "reviews" / "chapter" / f"{chapter:03d}" / "review_gate_status.md"
    if not gate_path.exists():
        raise RuntimeError("accepted review gate is missing")
    gate = gate_path.read_text(encoding="utf-8")
    if _gate_field(gate, "run_state") != "complete":
        raise RuntimeError("review gate is incomplete")
    if _gate_field(gate, "status") not in {"accepted", "accepted_with_notes"}:
        raise RuntimeError("review gate has not accepted the draft")
    current_hash = hashlib.sha256(draft.encode("utf-8")).hexdigest()
    if _gate_field(gate, "draft_sha256") != current_hash:
        raise RuntimeError("draft changed after its accepted review")
    if _gate_field(gate, "correctness_status") != "pass":
        raise RuntimeError("review gate lacks passing correctness evidence")
    if _gate_field(gate, "novelness_status") != "accept":
        raise RuntimeError("review gate lacks passing novelness evidence")
    reported_revision_resolution = _gate_field(gate, "revision_resolution_status")
    if reported_revision_resolution not in {"pass", "not_required"}:
        raise RuntimeError("review gate lacks complete revision comment resolution")

    novelness_path = story_path / "reviews" / "chapter" / f"{chapter:03d}" / "novelness_gate.md"
    if not novelness_path.exists():
        raise RuntimeError("Novelness Gate is missing")
    novelness = novelness_path.read_text(encoding="utf-8")
    if _gate_field(novelness, "status") != "accept":
        raise RuntimeError("Novelness Gate has not accepted the draft")
    if (
        _gate_field(novelness, "draft_sha256") != current_hash
        or _gate_field(novelness, "diagnostics_draft_sha256") != current_hash
    ):
        raise RuntimeError("Novelness Gate evidence does not match the draft")
    _validate_review_evidence(story_path, story_id, chapter, current_hash)
    revision_resolution, unresolved = revision_resolution_status(
        story_path,
        story_id,
        chapter,
        current_hash,
    )
    if revision_resolution != reported_revision_resolution or unresolved:
        raise RuntimeError(
            "revision comment resolution does not match current reviewer evidence: "
            + ", ".join(unresolved or [revision_resolution])
        )
    return gate_path


def _continuity_prompt(story_id: str, chapter: int, accepted_chapter: str) -> str:
    return f"""Create AcceptedContinuityV1 JSON from an accepted fiction chapter.

story_id: {story_id}
chapter: {chapter}

## Accepted Chapter
{accepted_chapter}

## Contract
- Derive every statement from the accepted chapter above.
- Record concrete events, decisions, discoveries, relationship changes, practical state, and unresolved pressure.
- Record the ending situation, intentions, relationship state, open pressure, reader questions, and continuity details needed next.
- Do not invent or interpret beyond the accepted text.
- Use empty arrays when the accepted chapter provides no evidence for a field.
- Return only one JSON object matching AcceptedContinuityV1.
"""


def _structured_repair_prompt(label: str, invalid_text: str, error: str) -> str:
    return f"""Repair invalid {label} JSON.

Validation error:
{error}

Invalid response:
{invalid_text}

Return only one corrected JSON object.
"""


def _grounding_prompt(
    story_id: str,
    chapter: int,
    accepted_chapter: str,
    continuity: dict[str, Any],
) -> str:
    return f"""Evaluate AcceptedContinuityV1 against its only allowed source.

story_id: {story_id}
chapter: {chapter}

## Accepted Chapter
{accepted_chapter}

## Candidate AcceptedContinuityV1
{json.dumps(continuity, ensure_ascii=False, indent=2)}

## Grounding Contract
- Mark every unsupported or over-interpreted claim.
- Mark every character or place name that conflicts with the accepted chapter.
- Detect `Thinking...`, `<think>`, chain-of-thought, or model-process traces anywhere in the candidate.
- grounded must be true only when all finding arrays are empty and thinking_trace_detected is false.
- Return only one JSON object matching AcceptanceGroundingDecisionV1.
"""


def _semantic_repair_prompt(
    story_id: str,
    chapter: int,
    accepted_chapter: str,
    continuity: dict[str, Any],
    grounding: dict[str, Any],
) -> str:
    return f"""Repair AcceptedContinuityV1 using the accepted chapter as the only source.

story_id: {story_id}
chapter: {chapter}

## Accepted Chapter
{accepted_chapter}

## Invalid Candidate
{json.dumps(continuity, ensure_ascii=False, indent=2)}

## Grounding Findings
{json.dumps(grounding, ensure_ascii=False, indent=2)}

Remove unsupported claims, correct name conflicts, and remove all model-process traces.
Return only one corrected JSON object matching AcceptedContinuityV1.
"""


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = load_yaml_text(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _prepare_state(story_path: Path, chapter: int) -> tuple[Path, str, Path, str]:
    chapter_path = story_path / "state" / "chapter_status.yaml"
    chapter_state = _load_yaml_mapping(chapter_path)
    chapter_state["current_chapter"] = chapter
    chapters = chapter_state.get("chapters")
    if not isinstance(chapters, dict):
        chapters = {}
    chapters[str(chapter)] = {"status": "accepted", "source": f"chapters/chapter_{chapter:03d}.md"}
    chapter_state["chapters"] = chapters
    chapter_content = dump_yaml(chapter_state, sort_keys=False)

    story_state_path = story_path / "state" / "story_status.yaml"
    story_state = _load_yaml_mapping(story_state_path)
    story_state["phase"] = "writing"
    story_state["active_chapter"] = chapter + 1
    story_state["last_accepted_chapter"] = chapter
    story_content = dump_yaml(story_state, sort_keys=False)
    return chapter_path, chapter_content, story_state_path, story_content


def _contains_thinking_trace(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False).lower()
    return any(marker in text for marker in ("thinking...", "<think>", "</think>", "chain-of-thought"))


def _write_acceptance_failure(
    story_path: Path,
    chapter: int,
    config: dict[str, Any],
    run_id: str,
    draft_path: Path,
    draft_sha256: str,
    stage: str,
    error: Exception | str,
    result: dict[str, Any] | None = None,
) -> None:
    write_run_provenance(
        story_path,
        chapter,
        "acceptance",
        result or {"model_profile": None, "attempts": []},
        config,
        {},
        {
            "run_id": run_id,
            "status": "failed",
            "source": str(draft_path.relative_to(story_path)),
            "draft_sha256": draft_sha256,
            "failed_stage": stage,
            "error": str(error),
        },
    )


def accept_draft(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    config_path: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Promote a current accepted draft and update derived continuity files."""
    story_path = resolve_story_path(workspace_path, story_id)
    draft_path = story_path / "drafts" / f"chapter_{chapter:03d}.md"
    if not draft_path.exists() or not draft_path.read_text(encoding="utf-8").strip():
        raise FileNotFoundError(f"draft is missing or empty: {draft_path}")
    draft = draft_path.read_text(encoding="utf-8")
    gate_path = _validate_gate(story_path, story_id, chapter, draft)
    config = load_config(config_path)
    require_explicit_runtime_config(config, "accepted chapter summary and handover")
    run_id = str(uuid4())
    draft_sha256 = hashlib.sha256(draft.encode("utf-8")).hexdigest()
    chain = select_model_for_stage(config, "handover_update", fallback_stage="chapter_generation")
    continuity_options = {
        **(options or {}),
        "output_schema_path": str(ACCEPTED_CONTINUITY_SCHEMA_PATH),
        "structured_output": True,
        "progress_label": "accepted continuity",
    }
    grounding_options = {
        **(options or {}),
        "output_schema_path": str(ACCEPTANCE_GROUNDING_SCHEMA_PATH),
        "structured_output": True,
        "progress_label": "acceptance grounding",
    }
    continuity_result = attempt_structured_model_chain(
        _continuity_prompt(story_id, chapter, draft),
        chain,
        config,
        lambda text: parse_accepted_continuity(text, story_id, chapter),
        lambda text, error: _structured_repair_prompt("AcceptedContinuityV1", text, error),
        continuity_options,
    )
    if not continuity_result.get("ok"):
        error = RuntimeError(
            f"accepted continuity failed for all configured models: {continuity_result.get('attempts', [])}"
        )
        _write_acceptance_failure(
            story_path,
            chapter,
            config,
            run_id,
            draft_path,
            draft_sha256,
            "accepted_continuity",
            error,
            continuity_result,
        )
        raise error
    continuity = continuity_result["value"]

    def check_grounding(candidate: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        result = attempt_structured_model_chain(
            _grounding_prompt(story_id, chapter, draft, candidate),
            chain,
            config,
            lambda text: parse_acceptance_grounding(text, story_id, chapter),
            lambda text, error: _structured_repair_prompt(
                "AcceptanceGroundingDecisionV1",
                text,
                error,
            ),
            grounding_options,
        )
        if not result.get("ok"):
            error = RuntimeError(
                f"acceptance grounding failed for all configured models: {result.get('attempts', [])}"
            )
            _write_acceptance_failure(
                story_path,
                chapter,
                config,
                run_id,
                draft_path,
                draft_sha256,
                "acceptance_grounding",
                error,
                result,
            )
            raise error
        decision = result["value"]
        if _contains_thinking_trace(candidate):
            decision = {**decision, "grounded": False, "thinking_trace_detected": True}
        return decision, result

    grounding, grounding_result = check_grounding(continuity)
    semantic_repair_result: dict[str, Any] | None = None
    second_grounding_result: dict[str, Any] | None = None
    if not grounding["grounded"]:
        semantic_repair_result = attempt_structured_model_chain(
            _semantic_repair_prompt(story_id, chapter, draft, continuity, grounding),
            chain,
            config,
            lambda text: parse_accepted_continuity(text, story_id, chapter),
            lambda text, error: _structured_repair_prompt("AcceptedContinuityV1", text, error),
            continuity_options,
        )
        if not semantic_repair_result.get("ok"):
            error = RuntimeError(
                f"accepted continuity semantic repair failed: {semantic_repair_result.get('attempts', [])}"
            )
            _write_acceptance_failure(
                story_path,
                chapter,
                config,
                run_id,
                draft_path,
                draft_sha256,
                "accepted_continuity_repair",
                error,
                semantic_repair_result,
            )
            raise error
        continuity = semantic_repair_result["value"]
        grounding, second_grounding_result = check_grounding(continuity)
        if not grounding["grounded"]:
            error = RuntimeError(f"accepted continuity remained ungrounded after one repair: {grounding}")
            _write_acceptance_failure(
                story_path,
                chapter,
                config,
                run_id,
                draft_path,
                draft_sha256,
                "acceptance_grounding_recheck",
                error,
                second_grounding_result,
            )
            raise error

    summary, handover = render_accepted_continuity(continuity)

    chapter_path = story_path / "chapters" / f"chapter_{chapter:03d}.md"
    summary_path = story_path / "summaries" / f"summary_chapter_{chapter:03d}.md"
    handover_path = story_path / "context" / "handover.md"
    chapter_state_path, chapter_state_content, story_state_path, story_state_content = _prepare_state(
        story_path,
        chapter,
    )
    attempts = [*continuity_result.get("attempts", []), *grounding_result.get("attempts", [])]
    if semantic_repair_result is not None:
        attempts.extend(semantic_repair_result.get("attempts", []))
    if second_grounding_result is not None:
        attempts.extend(second_grounding_result.get("attempts", []))
    provenance_payload = build_run_provenance_payload(
        chapter,
        "acceptance",
        {"model_profile": continuity_result.get("model_profile"), "attempts": attempts},
        config,
        {
            "accepted_chapter": str(chapter_path.relative_to(story_path)),
            "accepted_summary": str(summary_path.relative_to(story_path)),
            "handover": str(handover_path.relative_to(story_path)),
            "chapter_state": str(chapter_state_path.relative_to(story_path)),
            "story_state": str(story_state_path.relative_to(story_path)),
            "review_gate": str(gate_path.relative_to(story_path)),
        },
        {
            "run_id": run_id,
            "source": str(draft_path.relative_to(story_path)),
            "draft_sha256": draft_sha256,
            "grounding": grounding,
        },
    )

    prepared = (
        (chapter_path, draft),
        (summary_path, summary),
        (handover_path, handover),
        (chapter_state_path, chapter_state_content),
        (story_state_path, story_state_content),
    )
    for path, _ in prepared:
        assert_story_write_allowed(path, story_path)
    for path, content in prepared:
        safe_write_file(path, content, story_path)
    provenance_path = write_prepared_run_provenance(story_path, provenance_payload)
    return {
        "accepted_chapter": chapter_path,
        "accepted_summary": summary_path,
        "handover": handover_path,
        "chapter_state": chapter_state_path,
        "story_state": story_state_path,
        "provenance": provenance_path,
    }
