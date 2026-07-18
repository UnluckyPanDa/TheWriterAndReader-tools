"""Select and run configured model providers."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from shared.lib.codex_cli_runner import run_codex_cli_model
from shared.lib.config_loader import (
    CODEX_REASONING_EFFORTS,
    INTELLIGENCE_LEVELS,
    resolve_model_profile,
)
from shared.lib.local_cli_runner import run_local_cli_model
from shared.lib.online_api_runner import run_online_api_model


def get_fallback_chain(config: dict[str, Any], provider_group: str) -> list[dict[str, Any]]:
    """Resolve a provider group into ordered model profile dictionaries."""
    fallback_chains = config.get("fallback_chains", {})
    if provider_group not in fallback_chains:
        raise ValueError(f"Unknown provider group: {provider_group}")
    profile_names = fallback_chains[provider_group]
    if not isinstance(profile_names, list) or not profile_names:
        raise ValueError(f"Provider group '{provider_group}' must contain at least one profile")

    chain: list[dict[str, Any]] = []
    for profile_name in profile_names:
        profile = resolve_model_profile(config, str(profile_name))
        provider_name = profile.get("provider")
        provider_config = config.get("providers", {}).get(provider_name)
        if not isinstance(provider_config, dict):
            raise ValueError(f"Model profile '{profile_name}' references unknown provider '{provider_name}'")
        chain.append(
            {
                "profile_name": str(profile_name),
                "provider": provider_name,
                "provider_config": provider_config,
                **profile,
            }
        )
    return chain


def select_model_for_stage(
    config: dict[str, Any],
    stage_name: str,
    fallback_stage: str | None = None,
) -> list[dict[str, Any]]:
    """Select a writing-stage chain, optionally using a compatible stage."""
    stages = config.get("writing_stages", {})
    stage = stages.get(stage_name)
    if not isinstance(stage, dict) and fallback_stage:
        stage = stages.get(fallback_stage)
    if not isinstance(stage, dict):
        raise ValueError(f"Unknown writing stage: {stage_name}")
    provider_group = stage.get("provider_group")
    if not isinstance(provider_group, str):
        raise ValueError(f"Writing stage '{stage_name}' is missing provider_group")
    requested_intelligence = str(stage.get("intelligence", "medium"))
    mappings = config.get("writing_policy", {}).get("codex_intelligence_map", {})
    return _route_codex_intelligence(
        get_fallback_chain(config, provider_group),
        requested_intelligence,
        mappings,
        capability="writing",
    )


def select_model_for_reviewer(config: dict[str, Any], reviewer_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Select the fallback model chain for a reviewer definition."""
    provider_group = reviewer_config.get("provider_group")
    if not isinstance(provider_group, str):
        provider_group = config.get("review_policy", {}).get("provider_group", "local_first")
    requested_intelligence = str(reviewer_config.get("intelligence", "medium"))
    mappings = config.get("review_policy", {}).get("codex_intelligence_map", {})
    return _route_codex_intelligence(
        get_fallback_chain(config, provider_group),
        requested_intelligence,
        mappings,
        capability="review",
    )


def _route_codex_intelligence(
    chain: list[dict[str, Any]],
    requested_intelligence: str,
    mappings: Any,
    capability: str,
) -> list[dict[str, Any]]:
    """Apply a capability-specific model and reasoning mapping to Codex routes."""
    resolved: list[dict[str, Any]] = []
    for profile in chain:
        profile_intelligence = profile.get("intelligence")
        effective_intelligence = (
            str(profile_intelligence)
            if profile_intelligence in INTELLIGENCE_LEVELS
            else requested_intelligence
        )
        routed_profile = {
            **profile,
            "requested_intelligence": requested_intelligence,
            "resolved_intelligence": effective_intelligence,
        }
        provider_config = profile.get("provider_config", {})
        if not isinstance(provider_config, dict) or provider_config.get("type") != "codex_cli":
            resolved.append(routed_profile)
            continue
        provider_capability = provider_config.get("capability", "review")
        if provider_capability != capability:
            raise ValueError(
                f"Codex {provider_capability} provider cannot serve {capability} routing"
            )
        if requested_intelligence not in INTELLIGENCE_LEVELS:
            raise ValueError(f"Unknown {capability} intelligence: {requested_intelligence}")
        mapping = mappings.get(requested_intelligence) if isinstance(mappings, dict) else None
        if not isinstance(mapping, dict):
            label = "Codex" if capability == "review" else "Codex writing"
            raise ValueError(f"{label} intelligence mapping is missing: {requested_intelligence}")
        model = mapping.get("model")
        reasoning_effort = mapping.get("reasoning_effort")
        if (
            not isinstance(model, str)
            or not model.strip()
            or reasoning_effort not in CODEX_REASONING_EFFORTS
        ):
            label = "Codex" if capability == "review" else "Codex writing"
            raise ValueError(f"{label} intelligence mapping is invalid: {requested_intelligence}")
        resolved.append(
            {
                **routed_profile,
                "model": model,
                "reasoning_effort": reasoning_effort,
                "requested_intelligence": requested_intelligence,
                "resolved_intelligence": requested_intelligence,
            }
        )
    return resolved


def select_model_for_story_wizard(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Select the fallback model chain for story wizard tools."""
    provider_group = config.get("story_tools", {}).get("provider_group")
    if not isinstance(provider_group, str):
        raise ValueError("story_tools.provider_group is missing from config")
    return get_fallback_chain(config, provider_group)


def attempt_model_chain(
    prompt: str,
    model_chain: list[dict[str, Any]],
    config: dict[str, Any],
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attempt a prompt against a model chain until one provider succeeds."""
    options = options or {}
    attempts: list[dict[str, Any]] = []

    for model_profile in model_chain:
        result, attempt = _attempt_model_profile(prompt, model_profile, config, options)
        attempts.append(attempt)
        if result.get("ok"):
            return _success_result(result, model_profile, attempts)

    return {"ok": False, "text": "", "model_profile": None, "attempts": attempts}


def _attempt_model_profile(
    prompt: str,
    model_profile: dict[str, Any],
    config: dict[str, Any],
    options: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    profile_name = str(model_profile.get("profile_name", model_profile.get("model", "unknown")))
    provider_name = str(model_profile.get("provider", ""))
    provider_config = model_profile.get("provider_config", {})
    provider_type = provider_config.get("type") if isinstance(provider_config, dict) else None

    if not isinstance(provider_config, dict) or not provider_config.get("enabled", False):
        result = {"ok": False, "text": "", "reason": "provider_disabled"}
    elif provider_type == "mock" or provider_name == "mock":
        result = (
            {"ok": True, "text": _mock_response(prompt), "reason": None}
            if config.get("allow_mock", False)
            else {"ok": False, "text": "", "reason": "mock_provider_disabled"}
        )
    elif provider_type == "local_cli":
        result = run_local_cli_model(provider_config, model_profile, prompt, options)
    elif provider_type == "codex_cli":
        result = run_codex_cli_model(provider_config, model_profile, prompt, options)
    elif provider_type == "online_openai_compatible":
        result = run_online_api_model(provider_config, model_profile, prompt, options)
    else:
        result = {"ok": False, "text": "", "reason": f"unsupported_provider_type: {provider_type}"}

    attempt = {
        "model_profile": profile_name,
        "provider": provider_name,
        "provider_type": provider_type,
        "status": "success" if result.get("ok") else "failed",
        "reason": result.get("reason"),
    }
    _copy_result_metadata(attempt, result, model_profile)
    return result, attempt


def _copy_result_metadata(
    target: dict[str, Any],
    result: dict[str, Any],
    model_profile: dict[str, Any],
) -> None:
    for key in (
        "model",
        "reasoning_effort",
        "codex_profile",
        "capability",
        "orchestration",
        "requested_intelligence",
        "resolved_intelligence",
        "session",
        "usage",
    ):
        if key in result:
            target[key] = result[key]
        elif key in model_profile:
            target[key] = model_profile[key]


def _success_result(
    result: dict[str, Any],
    model_profile: dict[str, Any],
    attempts: list[dict[str, Any]],
    value: Any | None = None,
) -> dict[str, Any]:
    provider_config = model_profile.get("provider_config", {})
    success = {
        "ok": True,
        "text": str(result.get("text", "")),
        "model_profile": str(model_profile.get("profile_name", model_profile.get("model", "unknown"))),
        "provider": str(model_profile.get("provider", "")),
        "provider_type": provider_config.get("type") if isinstance(provider_config, dict) else None,
        "attempts": attempts,
    }
    if value is not None:
        success["value"] = value
    _copy_result_metadata(success, result, model_profile)
    return success


def attempt_structured_model_chain(
    prompt: str,
    model_chain: list[dict[str, Any]],
    config: dict[str, Any],
    validator: Callable[[str], Any],
    repair_prompt: Callable[[str, str], str],
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate initial and same-profile repair responses before fallback."""
    router_options = {**(options or {}), "structured_output": True}
    attempts: list[dict[str, Any]] = []
    for model_profile in model_chain:
        initial_result, initial_attempt = _attempt_model_profile(
            prompt,
            model_profile,
            config,
            router_options,
        )
        initial_attempt["phase"] = "initial"
        if not initial_result.get("ok"):
            attempts.append(initial_attempt)
            continue
        initial_text = str(initial_result.get("text", ""))
        try:
            value = validator(initial_text)
        except (TypeError, ValueError) as exc:
            initial_attempt.update(status="invalid", reason="validation_failed", validation_error=str(exc))
            attempts.append(initial_attempt)
        else:
            attempts.append(initial_attempt)
            return _success_result(initial_result, model_profile, attempts, value)

        repaired_result, repaired_attempt = _attempt_model_profile(
            repair_prompt(initial_text, str(initial_attempt["validation_error"])),
            model_profile,
            config,
            router_options,
        )
        repaired_attempt["phase"] = "repair"
        if not repaired_result.get("ok"):
            attempts.append(repaired_attempt)
            continue
        repaired_text = str(repaired_result.get("text", ""))
        try:
            value = validator(repaired_text)
        except (TypeError, ValueError) as exc:
            repaired_attempt.update(status="invalid", reason="validation_failed", validation_error=str(exc))
            attempts.append(repaired_attempt)
            continue
        attempts.append(repaired_attempt)
        return _success_result(repaired_result, model_profile, attempts, value)
    return {"ok": False, "text": "", "model_profile": None, "attempts": attempts}


def _mock_response(prompt: str) -> str:
    """Return deterministic text for tests and offline development."""
    lower = prompt.lower()
    if "acceptancegroundingdecisionv1" in lower:
        story_match = re.search(r"^story_id:\s*([^\s]+)$", prompt, re.MULTILINE)
        chapter_match = re.search(r"^chapter:\s*(\d+)$", prompt, re.MULTILINE)
        return json.dumps(
            {
                "schema_version": 1,
                "story_id": story_match.group(1) if story_match else "story-1",
                "chapter": int(chapter_match.group(1)) if chapter_match else 1,
                "grounded": True,
                "unsupported_claims": [],
                "name_conflicts": [],
                "thinking_trace_detected": False,
            },
            ensure_ascii=False,
        )
    if "acceptedcontinuityv1" in lower:
        story_match = re.search(r"^story_id:\s*([^\s]+)$", prompt, re.MULTILINE)
        chapter_match = re.search(r"^chapter:\s*(\d+)$", prompt, re.MULTILINE)
        return json.dumps(
            {
                "schema_version": 1,
                "story_id": story_match.group(1) if story_match else "story-1",
                "chapter": int(chapter_match.group(1)) if chapter_match else 1,
                "summary": {
                    "events": ["The protagonist enters the active situation."],
                    "decisions": ["The protagonist chooses action over hesitation."],
                    "discoveries": [],
                    "relationship_changes": [],
                    "practical_state": ["The immediate goal is reached."],
                    "unresolved_pressure": ["A larger question remains."],
                },
                "handover": {
                    "ending_situation": ["The immediate goal is complete while a larger question remains."],
                    "character_intentions": ["The protagonist intends to face the next consequence."],
                    "relationship_state": [],
                    "open_pressure": ["The larger question remains unresolved."],
                    "reader_questions": ["What consequence follows the decision?"],
                    "continuity_details": ["The protagonist chose action over hesitation."],
                },
            },
            ensure_ascii=False,
        )
    if "scene skeleton json" in lower:
        story_match = re.search(r"^story_id:\s*([^\s]+)$", prompt, re.MULTILINE)
        chapter_match = re.search(r"^chapter:\s*(\d+)$", prompt, re.MULTILINE)
        scene_ids = re.findall(r'"scene_id":\s*"([^"]+)"', prompt)
        story_id = story_match.group(1) if story_match else "story-1"
        chapter = int(chapter_match.group(1)) if chapter_match else 1
        scenes = [
            {
                "scene_id": scene_id,
                "purpose": "Force a binding choice under pressure.",
                "entry_condition": "The immediate problem remains unresolved.",
                "action_sequence": ["The protagonist enters the active situation.", "The protagonist chooses to act."],
                "conflict_escalation": ["Delay increases the cost."],
                "emotional_turns": ["Hesitation gives way to commitment."],
                "exit_condition": "The choice creates forward pressure.",
            }
            for scene_id in dict.fromkeys(scene_ids or ["scene-1"])
        ]
        return json.dumps(
            {
                "schema_version": 1,
                "story_id": story_id,
                "chapter": chapter,
                "scenes": scenes,
            },
            separators=(",", ":"),
        )
    if "scene contract json" in lower:
        story_match = re.search(r"^story_id:\s*([^\s]+)$", prompt, re.MULTILINE)
        chapter_match = re.search(r"^chapter:\s*(\d+)$", prompt, re.MULTILINE)
        story_id = story_match.group(1) if story_match else "story-1"
        chapter = int(chapter_match.group(1)) if chapter_match else 1
        return (
            '{"schema_version":1,"story_id":"'
            + story_id
            + '","chapter":'
            + str(chapter)
            + ',"chapter_progression":{"plot":"The task changes the practical situation.",'
            '"character":"The protagonist makes a binding choice.",'
            '"mystery":"The outcome creates a larger unanswered question."},'
            '"scenes":[{"scene_id":"scene-1","viewpoint_character":"protagonist",'
            '"starting_state":"The immediate problem is unresolved.",'
            '"immediate_goal":"Resolve the chapter task.",'
            '"pressure":"Delay will increase the cost.",'
            '"opposition":"The situation resists an easy solution.",'
            '"change_axes":["commitment"],'
            '"required_change":"The protagonist makes a binding choice.",'
            '"new_information":"The choice carries an immediate cost.",'
            '"physical_setting":"The active chapter location.",'
            '"active_characters":["protagonist"],'
            '"required_beats":["The protagonist acts under pressure."],'
            '"forbidden_reveals":[],"ending_turn":"The choice creates forward pressure."}]}'
        )
    if "review report" in lower or "reviewer" in lower or "review pack" in lower:
        reviewer_ids = re.findall(r"^reviewer_id:\s*([^\s]+)$", prompt, re.MULTILINE)
        reviewer_id = reviewer_ids[-1] if reviewer_ids else "mock_reviewer"
        reviewer_types = re.findall(r"^reviewer_type:\s*([^\s]+)$", prompt, re.MULTILINE)
        reviewer_type = reviewer_types[-1] if reviewer_types else "standard"
        story_ids = re.findall(r"^story_id:\s*([^\s]+)$", prompt, re.MULTILINE)
        story_id = story_ids[-1] if story_ids else "story-1"
        chapters = re.findall(r"^chapter:\s*(\d+)$", prompt, re.MULTILINE)
        chapter = int(chapters[-1]) if chapters else 1
        return json.dumps(
            {
                "schema_version": 1,
                "reviewer_id": reviewer_id,
                "reviewer_type": reviewer_type,
                "story_id": story_id,
                "chapter": chapter,
                "status": "pass",
                "summary": "The draft is coherent for the provided context.",
                "evidence": [
                    {
                        "location": "opening paragraph",
                        "observation": "The draft establishes the immediate situation.",
                        "reader_effect": "The scene is readable in this test fixture.",
                    }
                ],
                "severity_counts": {"blocker": 0, "major": 0, "minor": 0, "note": 0},
                "issues": [],
                "rewrite_recommendation": {"required": False, "scope": "none"},
                "gate_recommendation": "accept",
                "carry_forward_tasks": [],
                "reviewer_notes": ["Mock review completed."],
            },
            ensure_ascii=False,
        )
    if "polish this fiction chapter" in lower:
        heading_match = re.search(r"^(# (?:Chapter\s+\d+|第.+章))$", prompt, re.MULTILINE)
        heading = heading_match.group(1) if heading_match else "# Chapter 1"
        return (
            f"{heading}\n\nThe protagonist stepped into the active situation and chose action. "
            "The immediate goal was reached, and the choice created a larger obligation."
        )
    if "draft" in lower or "write the requested chapter" in lower or "chapter" in lower:
        return (
            "The morning opened with a quiet decision. The protagonist stepped into the "
            "scene carrying yesterday's doubts, but chose action over hesitation. By the "
            "end, the immediate goal was reached while a larger question remained."
        )
    if "pack" in lower:
        return "Mock model response for context pack request."
    return "Mock model response."
