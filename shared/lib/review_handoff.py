"""Prepare, execute, and apply review batches across private Git worktrees."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from shared.lib.config_loader import load_config
from shared.lib.path_rules import assert_story_write_allowed
from shared.lib.review_parser import (
    RFC3339_DATETIME,
    normalize_review_decision,
    parse_review_run_record,
    render_review_report,
    validate_review_run_record,
    validate_review_report,
)
from shared.lib.run_provenance import require_explicit_runtime_config, write_run_provenance
from shared.lib.safe_write import assert_inside_root, safe_write_file
from shared.lib.story_loader import load_story_context_file
from shared.lib.workspace_loader import resolve_story_path
from shared.lib.yaml_utils import load_yaml_text
from tools.review import run_review as review_runner


HANDOFF_SCHEMA_VERSION = 1


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return _sha256_text(_canonical_json(value))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid review handoff JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"review handoff JSON must be an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any], story_path: Path) -> Path:
    assert_story_write_allowed(path, story_path)
    return safe_write_file(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n", story_path)


def _review_root(story_path: Path, chapter: int) -> Path:
    return story_path / "reviews" / "chapter" / f"{chapter:03d}"


def _request_path(story_path: Path, chapter: int, handoff_id: str) -> Path:
    return _review_root(story_path, chapter) / "handoffs" / handoff_id / "request.json"


def _profile_hashes(story_path: Path, reviewer_config: dict[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for layer, key in (
        ("standard", "standard_reviewers"),
        ("series", "series_reviewers"),
        ("special", "special_reviewers"),
    ):
        reviewers = reviewer_config.get(key, {})
        if not isinstance(reviewers, dict):
            continue
        for reviewer_id, settings in sorted(reviewers.items()):
            if not isinstance(settings, dict) or not settings.get("enabled", True):
                continue
            if layer == "standard":
                profile_path = review_runner.REVIEWER_ROOT / f"{reviewer_id}.md"
            else:
                source = settings.get("source")
                if not isinstance(source, str) or not source.strip():
                    continue
                profile_path = story_path / source
            if profile_path.exists():
                hashes[f"{layer}.{reviewer_id}"] = _sha256_bytes(profile_path.read_bytes())
    return hashes


def _review_inputs(story_path: Path, story_id: str, chapter: int) -> dict[str, Any]:
    draft_path = story_path / "drafts" / f"chapter_{chapter:03d}.md"
    if not draft_path.exists() or not draft_path.read_text(encoding="utf-8").strip():
        raise FileNotFoundError(f"draft is missing or empty: {draft_path}")
    pack_path = story_path / "context" / "review_pack.md"
    if not pack_path.exists() or not pack_path.read_text(encoding="utf-8").strip():
        raise FileNotFoundError(f"review pack is missing or empty: {pack_path}")
    reviewer_config_path = story_path / "reviewers" / "reviewer_config.yaml"
    reviewer_config = load_yaml_text(reviewer_config_path.read_text(encoding="utf-8")) if reviewer_config_path.exists() else {}
    if not isinstance(reviewer_config, dict):
        reviewer_config = {}
    expected: list[dict[str, Any]] = []
    for layer, key in (
        ("standard", "standard_reviewers"),
        ("series", "series_reviewers"),
        ("special", "special_reviewers"),
    ):
        reviewers = reviewer_config.get(key, {})
        if not isinstance(reviewers, dict):
            continue
        for reviewer_id, settings in sorted(reviewers.items()):
            if isinstance(settings, dict) and settings.get("enabled", True):
                expected.append(
                    {
                        "layer": layer,
                        "reviewer_id": str(reviewer_id),
                        "can_block_gate": bool(settings.get("can_block_gate", True)),
                    }
                )
    core = {
        "story_id": story_id,
        "chapter": chapter,
        "draft_sha256": _sha256_bytes(draft_path.read_bytes()),
        "review_pack_sha256": _sha256_bytes(pack_path.read_bytes()),
        "reviewer_config_sha256": _sha256_bytes(reviewer_config_path.read_bytes()) if reviewer_config_path.exists() else "missing",
        "profile_sha256": _profile_hashes(story_path, reviewer_config),
        "expected_reviewers": expected,
    }
    core["input_fingerprint"] = _digest(core)
    return core


def _load_request(path: str | Path, story_path: Path, story_id: str, chapter: int) -> dict[str, Any]:
    request_path = Path(path).expanduser().resolve(strict=True)
    assert_inside_root(request_path, story_path)
    request = _read_json(request_path)
    if request.get("schema_version") != HANDOFF_SCHEMA_VERSION or request.get("handoff_type") != "review":
        raise RuntimeError("unsupported review handoff request")
    for field, expected in (("story_id", story_id), ("chapter", chapter)):
        if request.get(field) != expected:
            raise RuntimeError(f"review handoff request {field} must be {expected!r}")
    digest = request.get("request_digest")
    core = {key: value for key, value in request.items() if key != "request_digest"}
    if not isinstance(digest, str) or digest != _digest(core):
        raise RuntimeError("review handoff request digest is invalid or tampered")
    current = _review_inputs(story_path, story_id, chapter)
    if request.get("draft_sha256") != current["draft_sha256"]:
        raise RuntimeError("review handoff request is stale: draft SHA changed")
    if request.get("input_fingerprint") != current["input_fingerprint"]:
        raise RuntimeError("review handoff request is stale: review-input fingerprint changed")
    request["_path"] = request_path
    return request


def prepare_review_handoff(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
) -> Path:
    """Create an immutable review request without running a reviewer."""
    story_path = resolve_story_path(workspace_path, story_id)
    review_pack_path = review_runner.build_review_pack(workspace_path, story_id, chapter)
    inputs = _review_inputs(story_path, story_id, chapter)
    handoff_id = str(uuid4())
    request = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "handoff_type": "review",
        "handoff_id": handoff_id,
        "created_at": datetime.now(UTC).isoformat(),
        "story_id": story_id,
        "chapter": chapter,
        "draft": f"drafts/chapter_{chapter:03d}.md",
        "draft_sha256": inputs["draft_sha256"],
        "review_pack": str(review_pack_path.relative_to(story_path)),
        "review_pack_sha256": inputs["review_pack_sha256"],
        "reviewer_config_sha256": inputs["reviewer_config_sha256"],
        "profile_sha256": inputs["profile_sha256"],
        "expected_reviewers": inputs["expected_reviewers"],
        "input_fingerprint": inputs["input_fingerprint"],
        "execution": {"one_active_writer_per_chapter": True, "apply_mode": "gate_last"},
    }
    request["request_digest"] = _digest(request)
    return _write_json(_request_path(story_path, chapter, handoff_id), request, story_path)


def _execution_root(story_path: Path, chapter: int, execution_id: str) -> Path:
    return story_path / "runs" / f"chapter_{chapter:03d}" / execution_id / "review_handoff"


def _write_execution_record(
    root: Path,
    story_path: Path,
    layer: str,
    reviewer_id: str,
    record: dict[str, Any],
    normalization: dict[str, Any],
) -> tuple[Path, Path, Path]:
    label = f"{layer}.{reviewer_id}"
    record_path = root / "records" / f"{label}.json"
    report_path = root / "records" / f"{label}.md"
    receipt_path = root / "records" / f"{label}.normalization.json"
    record = deepcopy(record)
    record["outputs"] = {
        "decision_json": str(record_path.relative_to(story_path)),
        "report_markdown": str(report_path.relative_to(story_path)),
    }
    errors = validate_review_run_record(record)
    if errors:
        raise RuntimeError(f"review handoff record is invalid: {', '.join(errors)}")
    report = render_review_report(record["decision"], record)
    report_errors = validate_review_report(report, reviewer_id)
    if report_errors:
        raise RuntimeError(f"review handoff report is invalid: {', '.join(report_errors)}")
    _write_json(record_path, record, story_path)
    assert_story_write_allowed(report_path, story_path)
    safe_write_file(report_path, report, story_path)
    receipt = {
        **normalization,
        "run_id": record["run_id"],
        "draft_sha256": record["draft_sha256"],
        "canonical_record": record,
        "raw_response_text": normalization.get("raw_response_text", ""),
    }
    _write_json(receipt_path, receipt, story_path)
    return record_path, report_path, receipt_path


def execute_review_handoff(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    request_path: str | Path,
    config_path: str | None = None,
    options: dict[str, Any] | None = None,
) -> Path:
    """Execute a prepared request and write only append-only result artifacts."""
    story_path = resolve_story_path(workspace_path, story_id)
    request = _load_request(request_path, story_path, story_id, chapter)
    config = load_config(config_path)
    require_explicit_runtime_config(config, "review handoff execution")
    execution_id = str(uuid4())
    root = _execution_root(story_path, chapter, execution_id)
    review_pack = load_story_context_file(story_path, "review_pack.md")
    reviewer_config_path = story_path / "reviewers" / "reviewer_config.yaml"
    reviewer_config = load_yaml_text(reviewer_config_path.read_text(encoding="utf-8")) if reviewer_config_path.exists() else {}
    reviewer_config = reviewer_config if isinstance(reviewer_config, dict) else {}
    draft_sha256 = str(request["draft_sha256"])
    records: list[dict[str, Any]] = []
    record_paths: list[Path] = []
    attempts: list[dict[str, Any]] = []
    try:
        specs: list[tuple[str, str, dict[str, Any]]] = []
        for item in request["expected_reviewers"]:
            layer = str(item["layer"])
            reviewer_id = str(item["reviewer_id"])
            key = {"standard": "standard_reviewers", "series": "series_reviewers", "special": "special_reviewers"}[layer]
            settings = reviewer_config.get(key, {}).get(reviewer_id, {})
            if not isinstance(settings, dict):
                raise RuntimeError(f"reviewer settings are missing: {layer}.{reviewer_id}")
            specs.append((layer, reviewer_id, settings))
        router_options = {**(options or {}), "flexible_output": True, "preserve_raw_response": True}
        for layer, reviewer_id, settings in specs:
            profile = review_runner._reviewer_profile(story_path, layer, reviewer_id, settings)
            prior = []
            semantic_normalizer = review_runner._configured_semantic_normalizer(
                config,
                settings,
                story_id,
                chapter,
                review_pack,
            )
            result = review_runner.attempt_structured_model_chain(
                review_runner._review_prompt(story_id, chapter, layer, reviewer_id, settings, profile, review_pack, prior),
                review_runner._model_chain(config, settings),
                config,
                lambda text, current_id=reviewer_id, current_layer=layer, normalizer=semantic_normalizer: normalize_review_decision(
                    text, current_id, current_layer, story_id, chapter, normalizer
                )["canonical"],
                lambda text, error, current_id=reviewer_id, current_layer=layer: review_runner._review_repair_prompt(
                    story_id, chapter, current_layer, current_id, text, error
                ),
                router_options,
            )
            attempts.extend(result.get("attempts", []))
            if not result.get("ok"):
                raise RuntimeError(f"reviewer {reviewer_id} failed for all configured models: {result.get('attempts', [])}")
            report_path, record_path, record, normalization = review_runner._write_review_report(
                story_path, chapter, layer, reviewer_id, story_id, result, execution_id, draft_sha256, False
            )
            written_record, _, _ = _write_execution_record(
                root, story_path, layer, reviewer_id, record, normalization
            )
            record_paths.append(written_record)
            records.append({"layer": layer, "reviewer_id": reviewer_id, "record": str(written_record.relative_to(story_path))})
        manifest = {
            "schema_version": HANDOFF_SCHEMA_VERSION,
            "handoff_type": "review_result",
            "status": "complete",
            "execution_id": execution_id,
            "request_path": str(Path(request_path).resolve().relative_to(story_path)),
            "request_digest": request["request_digest"],
            "story_id": story_id,
            "chapter": chapter,
            "draft_sha256": draft_sha256,
            "input_fingerprint": request["input_fingerprint"],
            "records": records,
            "record_sha256": {str(path.relative_to(story_path)): _sha256_bytes(path.read_bytes()) for path in record_paths},
            "created_at": datetime.now(UTC).isoformat(),
            "attempts": attempts,
        }
    except Exception as exc:
        manifest = {
            "schema_version": HANDOFF_SCHEMA_VERSION,
            "handoff_type": "review_result",
            "status": "failed",
            "execution_id": execution_id,
            "request_path": str(Path(request_path).resolve().relative_to(story_path)),
            "request_digest": request["request_digest"],
            "story_id": story_id,
            "chapter": chapter,
            "draft_sha256": draft_sha256,
            "input_fingerprint": request["input_fingerprint"],
            "records": [],
            "attempts": attempts,
            "error": str(exc),
            "created_at": datetime.now(UTC).isoformat(),
        }
    manifest["result_digest"] = _digest(manifest)
    result_path = root / "review_result.json"
    _write_json(result_path, manifest, story_path)
    if manifest["status"] != "complete":
        raise RuntimeError(f"review handoff execution failed: {manifest['error']}")
    return result_path


def _compatible_record(
    path: Path,
    story_path: Path,
    story_id: str,
    chapter: int,
    layer: str,
    reviewer_id: str,
    run_id: str,
    draft_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    source_text = text
    source_format_override: str | None = None
    if "# Combined Review" in text:
        match = re.search(
            rf"^##\s+{re.escape(layer)}\.{re.escape(reviewer_id)}\s*$([\s\S]*?)(?=^##\s+|\Z)",
            text,
            re.MULTILINE,
        )
        if match:
            source_text = match.group(1).strip()
            source_format_override = "combined_review"
    try:
        data = json.loads(source_text)
    except json.JSONDecodeError:
        data = None
    normalization: dict[str, Any]
    if isinstance(data, dict) and isinstance(data.get("decision"), dict):
        try:
            record = parse_review_run_record(text)
            receipt_path = path.with_suffix(".normalization.json")
            if receipt_path.exists():
                normalization = _read_json(receipt_path)
            else:
                normalization = {"source_format": "review_run_record_v1", "normalization_method": "trusted_v1", "inferred_fields": [], "warnings": [], "raw_response_text": text}
            return record, normalization
        except ValueError:
            decision_source = data["decision"]
            source_format = "legacy_review_run_record"
    else:
        decision_source = data if isinstance(data, dict) else source_text
        source_format = "legacy_result_bundle" if isinstance(data, dict) else "legacy_markdown"
    if source_format_override:
        source_format = source_format_override
    raw = json.dumps(decision_source, ensure_ascii=False) if isinstance(decision_source, dict) else str(decision_source)
    normalized = normalize_review_decision(raw, reviewer_id, layer, story_id, chapter)
    decision = normalized["canonical"]
    provider = data.get("provider", {}) if isinstance(data, dict) else {}
    provider = provider if isinstance(provider, dict) else {}
    recorded_at = data.get("recorded_at") if isinstance(data, dict) else None
    if not isinstance(recorded_at, str) or not RFC3339_DATETIME.fullmatch(recorded_at):
        recorded_at = datetime.now(UTC).isoformat()
    record = {
        "schema_version": 1,
        "run_id": str(data.get("run_id") or run_id) if isinstance(data, dict) else run_id,
        "recorded_at": recorded_at,
        "draft_sha256": str(data.get("draft_sha256") or draft_sha256) if isinstance(data, dict) else draft_sha256,
        "reviewer": {"id": reviewer_id, "type": layer},
        "provider": {
            "id": str(provider.get("id") or "legacy"),
            "type": str(provider.get("type") or "legacy"),
            "model_profile": str(provider.get("model_profile") or "legacy"),
            "codex_profile": provider.get("codex_profile"),
            "model": provider.get("model"),
            "reasoning_effort": provider.get("reasoning_effort"),
            "requested_intelligence": provider.get("requested_intelligence"),
            "resolved_intelligence": provider.get("resolved_intelligence"),
            "orchestration": str(provider.get("orchestration") or "direct"),
        },
        "session": data.get("session") if isinstance(data, dict) and isinstance(data.get("session"), dict) else None,
        "usage": data.get("usage", {}) if isinstance(data, dict) and isinstance(data.get("usage"), dict) else {},
        "outputs": {
            "decision_json": str(path.relative_to(story_path)),
            "report_markdown": str(path.with_suffix(".md").relative_to(story_path)),
        },
        "decision": decision,
    }
    errors = validate_review_run_record(record)
    if errors:
        raise RuntimeError(f"legacy review record cannot be normalized: {', '.join(errors)}")
    normalization = {
        **normalized,
        "source_format": source_format,
        "normalization_method": "legacy_record_import",
        "raw_response_text": text,
        "canonical_record": record,
    }
    return record, normalization


def apply_review_handoff(
    workspace_path: str | Path,
    story_id: str,
    chapter: int,
    request_path: str | Path,
    result_path: str | Path,
) -> dict[str, Path | str]:
    """Validate and atomically promote a complete review result batch."""
    story_path = resolve_story_path(workspace_path, story_id)
    request = _load_request(request_path, story_path, story_id, chapter)
    result_file = Path(result_path).expanduser().resolve(strict=True)
    assert_inside_root(result_file, story_path)
    manifest = _read_json(result_file)
    digest = manifest.get("result_digest")
    unsigned = {key: value for key, value in manifest.items() if key != "result_digest"}
    if not isinstance(digest, str) or digest != _digest(unsigned):
        raise RuntimeError("review handoff result digest is invalid or tampered")
    if manifest.get("status") != "complete":
        raise RuntimeError("cannot apply an incomplete or failed review result")
    for field, expected in (("story_id", story_id), ("chapter", chapter), ("request_digest", request["request_digest"]), ("draft_sha256", request["draft_sha256"]), ("input_fingerprint", request["input_fingerprint"])):
        if manifest.get(field) != expected:
            raise RuntimeError(f"review handoff result {field} does not match the request/current story")
    current = _review_inputs(story_path, story_id, chapter)
    if current["draft_sha256"] != manifest["draft_sha256"] or current["input_fingerprint"] != manifest["input_fingerprint"]:
        raise RuntimeError("review handoff result is stale: draft or review-input fingerprint changed")
    expected = {(str(item["layer"]), str(item["reviewer_id"])) for item in request["expected_reviewers"]}
    entries = manifest.get("records")
    if not isinstance(entries, list) or {(str(item.get("layer")), str(item.get("reviewer_id"))) for item in entries if isinstance(item, dict)} != expected:
        raise RuntimeError("review handoff result is partial or has an unexpected reviewer set")
    run_id = str(manifest.get("execution_id"))
    validated: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    record_hashes = manifest.get("record_sha256", {})
    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError("review handoff result contains an invalid record entry")
        layer, reviewer_id = str(entry["layer"]), str(entry["reviewer_id"])
        if (layer, reviewer_id) in seen:
            raise RuntimeError("review handoff result mixes duplicate reviewer records")
        seen.add((layer, reviewer_id))
        record_path = (story_path / str(entry["record"])).resolve(strict=True)
        assert_inside_root(record_path, story_path)
        expected_hash = record_hashes.get(str(record_path.relative_to(story_path)))
        if expected_hash != _sha256_bytes(record_path.read_bytes()):
            raise RuntimeError(f"review handoff record is tampered: {record_path.name}")
        record, normalization = _compatible_record(
            record_path, story_path, story_id, chapter, layer, reviewer_id, run_id, str(manifest["draft_sha256"])
        )
        if record["run_id"] != run_id or record["draft_sha256"] != manifest["draft_sha256"] or record["reviewer"] != {"id": reviewer_id, "type": layer}:
            raise RuntimeError("review handoff result mixes runs or identities")
        validated.append((layer, reviewer_id, record, normalization))

    gate_path = review_runner._gate_path(story_path, chapter)
    already_applied = gate_path.exists() and f"run_id: {run_id}" in gate_path.read_text(encoding="utf-8")
    if already_applied:
        for layer, reviewer_id, record, _ in validated:
            current_path = review_runner._review_record_path(story_path, chapter, layer, reviewer_id)
            expected_current = deepcopy(record)
            expected_current["outputs"] = {
                "decision_json": str(current_path.relative_to(story_path)),
                "report_markdown": str(review_runner._report_path(story_path, chapter, layer, reviewer_id).relative_to(story_path)),
            }
            if not current_path.exists() or json.loads(current_path.read_text(encoding="utf-8")) != expected_current:
                already_applied = False
                break
    if already_applied:
        return {"status": "already_applied", "review_gate": gate_path}

    # All content is validated before any current record, combined report, or gate is written.
    for layer, reviewer_id, record, normalization in validated:
        current_record = deepcopy(record)
        current_record["outputs"] = {
            "decision_json": str(review_runner._review_record_path(story_path, chapter, layer, reviewer_id).relative_to(story_path)),
            "report_markdown": str(review_runner._report_path(story_path, chapter, layer, reviewer_id).relative_to(story_path)),
        }
        review_runner._write_review_history(story_path, chapter, layer, reviewer_id, current_record, normalization)
        review_runner._promote_review_record(
            story_path,
            review_runner._report_path(story_path, chapter, layer, reviewer_id),
            review_runner._review_record_path(story_path, chapter, layer, reviewer_id),
            current_record,
            normalization,
        )
    gates = review_runner.rebuild_review_gate(workspace_path, story_id, chapter, run_id=run_id)
    write_run_provenance(
        story_path,
        chapter,
        "review_apply",
        {"model_profile": "handoff", "attempts": []},
        {"_source_path": "review-handoff"},
        {name: str(path.relative_to(story_path)) for name, path in gates.items()},
        {"run_id": run_id, "request_digest": request["request_digest"], "input_fingerprint": request["input_fingerprint"], "draft_sha256": manifest["draft_sha256"]},
    )
    return {"status": "applied", **gates}
