"""Select and run configured model providers."""

from __future__ import annotations

import re
from typing import Any

from shared.lib.config_loader import resolve_model_profile
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
    return get_fallback_chain(config, provider_group)


def select_model_for_reviewer(config: dict[str, Any], reviewer_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Select the fallback model chain for a reviewer definition."""
    provider_group = reviewer_config.get("provider_group")
    if not isinstance(provider_group, str):
        provider_group = config.get("review_policy", {}).get("provider_group", "local_first")
    return get_fallback_chain(config, provider_group)


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
        profile_name = str(model_profile.get("profile_name", model_profile.get("model", "unknown")))
        provider_name = str(model_profile.get("provider", ""))
        provider_config = model_profile.get("provider_config", {})
        provider_type = provider_config.get("type") if isinstance(provider_config, dict) else None

        if not isinstance(provider_config, dict) or not provider_config.get("enabled", False):
            result = {"ok": False, "text": "", "reason": "provider_disabled"}
        elif provider_type == "mock" or provider_name == "mock":
            if config.get("allow_mock", False):
                result = {"ok": True, "text": _mock_response(prompt), "reason": None}
            else:
                result = {"ok": False, "text": "", "reason": "mock_provider_disabled"}
        elif provider_type == "local_cli":
            result = run_local_cli_model(provider_config, model_profile, prompt, options)
        elif provider_type == "online_openai_compatible":
            result = run_online_api_model(provider_config, model_profile, prompt, options)
        else:
            result = {"ok": False, "text": "", "reason": f"unsupported_provider_type: {provider_type}"}

        attempts.append(
            {
                "model_profile": profile_name,
                "provider": provider_name,
                "status": "success" if result.get("ok") else "failed",
                "reason": result.get("reason"),
            }
        )
        if result.get("ok"):
            return {
                "ok": True,
                "text": str(result.get("text", "")),
                "model_profile": profile_name,
                "attempts": attempts,
            }

    return {"ok": False, "text": "", "model_profile": None, "attempts": attempts}


def _mock_response(prompt: str) -> str:
    """Return deterministic text for tests and offline development."""
    lower = prompt.lower()
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
            + ',"scenes":[{"scene_id":"scene-1","viewpoint_character":"protagonist",'
            '"starting_state":"The immediate problem is unresolved.",'
            '"immediate_goal":"Resolve the chapter task.",'
            '"pressure":"Delay will increase the cost.",'
            '"opposition":"The situation resists an easy solution.",'
            '"change_axes":["commitment"],'
            '"required_change":"The protagonist makes a binding choice.",'
            '"physical_setting":"The active chapter location.",'
            '"active_characters":["protagonist"],'
            '"required_beats":["The protagonist acts under pressure."],'
            '"forbidden_reveals":[],"ending_turn":"The choice creates forward pressure."}]}'
        )
    if "review report" in lower or "reviewer" in lower or "review pack" in lower:
        reviewer_ids = re.findall(r"^reviewer_id:\s*([^\s]+)$", prompt, re.MULTILINE)
        reviewer_id = reviewer_ids[-1] if reviewer_ids else "mock_reviewer"
        return f"""# Review Report
reviewer_id: {reviewer_id}
reviewer_type: mock
story_id: story-1
chapter: 1
draft_file: mock
status: pass
## Summary
The draft is coherent for the provided context.
## Evidence
- Location: opening paragraph
  Observation: the draft establishes the immediate situation.
  Reader effect: the scene is readable in this test fixture.
## Severity Counts
- blocker: 0
- major: 0
- minor: 0
- note: 0
## Issues
## Rewrite Recommendation
rewrite_required: no
rewrite_scope: none
## Gate Recommendation
gate_status: accept
## Carry-Forward Tasks
None.
## Reviewer Notes
Mock review completed."""
    if "draft" in lower or "write the requested chapter" in lower or "chapter" in lower:
        return (
            "The morning opened with a quiet decision. The protagonist stepped into the "
            "scene carrying yesterday's doubts, but chose action over hesitation. By the "
            "end, the immediate goal was reached while a larger question remained."
        )
    if "pack" in lower:
        return "Mock model response for context pack request."
    return "Mock model response."
