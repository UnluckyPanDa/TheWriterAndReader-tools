"""Load, validate, export, and import external tool configuration."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

from shared.lib.yaml_utils import dump_yaml, load_yaml_text

SECRET_KEYS = {"api_key", "api_key_env", "token", "secret", "password"}


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
    providers = config.get("providers", {})
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
