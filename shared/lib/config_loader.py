"""Load, validate, export, and import external tool configuration."""
from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any

from shared.lib.yaml_utils import dump_yaml, load_yaml_text

SECRET_KEYS = {"api_key", "api_key_env", "token", "secret", "password"}
INTELLIGENCE_LEVELS = ("low", "medium", "high", "very_high")
CODEX_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}
CODEX_CAPABILITIES = {"review", "writing"}
CODEX_AGENT_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_codex_intelligence_map(
    config: dict[str, Any],
    policy_key: str,
    label: str,
) -> list[str]:
    policy = config.get(policy_key, {})
    mappings = policy.get("codex_intelligence_map") if isinstance(policy, dict) else None
    if not isinstance(mappings, dict):
        return [f"{policy_key}.codex_intelligence_map must be a mapping"]
    messages: list[str] = []
    for level in INTELLIGENCE_LEVELS:
        mapping = mappings.get(level)
        if not isinstance(mapping, dict):
            messages.append(f"{label} intelligence mapping is missing: {level}")
            continue
        if not isinstance(mapping.get("model"), str) or not str(mapping.get("model", "")).strip():
            messages.append(f"{label} intelligence mapping {level} requires a model")
        if mapping.get("reasoning_effort") not in CODEX_REASONING_EFFORTS:
            messages.append(f"{label} intelligence mapping {level} has invalid reasoning_effort")
    return messages


def get_default_config_path() -> Path:
    """Return the default external config path, honoring TWR_CONFIG."""
    configured = os.environ.get("TWR_CONFIG")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".config" / "the-writer-and-reader" / "config.yaml"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file as a dictionary."""
    if not path.exists():
        raise FileNotFoundError(f"YAML file does not exist: {path}")
    data = load_yaml_text(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping at top level: {path}")
    return data


def load_config_example(tools_repo_path: str | Path | None = None) -> dict[str, Any]:
    """Load config.example.yaml from the tools repository."""
    root = Path(tools_repo_path).expanduser().resolve() if tools_repo_path else _repo_root()
    path = root / "config.example.yaml"
    if not path.exists() and tools_repo_path is None:
        path = Path(__file__).resolve().parents[1] / "templates" / "config.example.yaml"
    config = load_yaml(path)
    config["_source_path"] = str(path)
    config["_used_example_config"] = True
    return config


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load external config, falling back to config.example.yaml when missing."""
    path = Path(config_path).expanduser() if config_path else get_default_config_path()
    if path.exists():
        config = load_yaml(path)
        config["_source_path"] = str(path)
        config["_used_example_config"] = False
        return config
    config = load_config_example()
    config["_missing_external_config"] = str(path)
    return config


def validate_config(config: dict[str, Any]) -> list[str]:
    """Return validation messages for required config structure."""
    messages: list[str] = []
    for key in ("providers", "model_profiles", "fallback_chains"):
        if not isinstance(config.get(key), dict):
            messages.append(f"missing or invalid config key: {key}")
    configured_providers = config.get("providers", {})
    providers = configured_providers if isinstance(configured_providers, dict) else {}
    codex_capabilities: set[str] = set()
    for name, provider in providers.items():
        if not isinstance(provider, dict) or provider.get("type") != "codex_cli":
            continue
        capability = provider.get("capability", "review")
        if capability not in CODEX_CAPABILITIES:
            messages.append(f"Codex provider {name} capability must be review or writing")
        else:
            codex_capabilities.add(str(capability))
        if not isinstance(provider.get("command"), str) or not str(provider.get("command", "")).strip():
            messages.append(f"Codex provider {name} requires a non-empty command")
        if not isinstance(provider.get("profile"), str) or not str(provider.get("profile", "")).strip():
            messages.append(f"Codex provider {name} requires a dedicated profile")
        codex_home_value = provider.get("codex_home")
        if not isinstance(codex_home_value, str) or not codex_home_value.strip():
            messages.append(f"Codex provider {name} requires a dedicated codex_home")
        elif not Path(codex_home_value).expanduser().is_absolute():
            messages.append(f"Codex provider {name} codex_home must be an absolute path")
        session = provider.get("session")
        if not isinstance(session, dict):
            messages.append(f"Codex provider {name} session must be a mapping")
        else:
            if session.get("start_mode") != "fresh":
                messages.append(f"Codex provider {name} only supports session.start_mode fresh")
            if session.get("retention") not in {"persisted", "ephemeral"}:
                messages.append(
                    f"Codex provider {name} session.retention must be persisted or ephemeral"
                )
        subagents = provider.get("subagents")
        if subagents is not None and not isinstance(subagents, dict):
            messages.append(f"Codex provider {name} subagents must be a mapping")
        elif isinstance(subagents, dict):
            required = subagents.get("required", False)
            if not isinstance(required, bool):
                messages.append(f"Codex provider {name} subagents.required must be a boolean")
            elif required:
                if capability != "review":
                    messages.append(f"Codex writing provider {name} cannot require review subagents")
                count = subagents.get("count")
                if type(count) is not int or count != 1:
                    messages.append(f"Codex provider {name} subagents.count must be exactly 1")
                agent = subagents.get("agent")
                if not isinstance(agent, str) or not CODEX_AGENT_NAME.fullmatch(agent):
                    messages.append(f"Codex provider {name} subagents.agent must be a safe agent name")
    for name, provider in config.get("model_profiles", {}).items():
        if not isinstance(provider, dict):
            messages.append(f"model profile {name} must be a mapping")
            continue
        provider_name = provider.get("provider")
        if provider_name not in providers:
            messages.append(f"model profile {name} references unknown provider {provider_name}")
    for group, profiles in config.get("fallback_chains", {}).items():
        if not isinstance(profiles, list) or not profiles:
            messages.append(f"fallback chain {group} must be a non-empty list")
            continue
        for profile in profiles:
            if profile not in config.get("model_profiles", {}):
                messages.append(f"fallback chain {group} references unknown profile {profile}")
    if "review" in codex_capabilities:
        messages.extend(_validate_codex_intelligence_map(config, "review_policy", "Codex"))
    if "writing" in codex_capabilities:
        messages.extend(_validate_codex_intelligence_map(config, "writing_policy", "Codex writing"))
    return messages


def _strip_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key.startswith("_"):
                continue
            if key.lower() in SECRET_KEYS:
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = _strip_secrets(item)
        return cleaned
    if isinstance(value, list):
        return [_strip_secrets(item) for item in value]
    return value


def export_config(config: dict[str, Any], output_path: str | Path, mode: str = "no-secrets") -> Path:
    """Export config to a path, redacting secrets unless full-with-secrets is requested."""
    target = Path(output_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = copy.deepcopy(config) if mode == "full-with-secrets" else _strip_secrets(config)
    target.write_text(dump_yaml(data, sort_keys=False), encoding="utf-8")
    return target


def import_config(input_path: str | Path, target_path: str | Path | None = None) -> Path:
    """Validate and copy a config file into the external config location."""
    source = Path(input_path).expanduser()
    config = load_yaml(source)
    messages = validate_config(config)
    if messages:
        raise ValueError("config import failed: " + "; ".join(messages))
    target = Path(target_path).expanduser() if target_path else get_default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def resolve_provider_group(config: dict[str, Any], group_name: str) -> list[str]:
    """Resolve a fallback provider group into model profile names."""
    chains = config.get("fallback_chains", {})
    if group_name not in chains:
        raise KeyError(f"unknown provider group: {group_name}")
    profiles = chains[group_name]
    if not isinstance(profiles, list) or not profiles:
        raise ValueError(f"provider group {group_name} must be a non-empty list")
    return [str(profile) for profile in profiles]


def resolve_model_profile(config: dict[str, Any], profile_name: str) -> dict[str, Any]:
    """Resolve a model profile by name and include its profile_name."""
    profiles = config.get("model_profiles", {})
    if profile_name not in profiles:
        raise KeyError(f"unknown model profile: {profile_name}")
    profile = dict(profiles[profile_name])
    profile["profile_name"] = profile_name
    return profile
