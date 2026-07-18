"""Idempotent first-run setup for an installed TWR runtime."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

from shared.lib.config_loader import get_default_config_path, load_config_example
from shared.lib.safe_write import atomic_write
from shared.lib.yaml_utils import dump_yaml


def _discover_ollama_models(base_url: str) -> list[str]:
    try:
        import requests

        response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=3.0)
        response.raise_for_status()
        body = response.json()
    except Exception:
        return []
    models = body.get("models", []) if isinstance(body, dict) else []
    return sorted(
        {
            str(item.get("model") or item.get("name"))
            for item in models
            if isinstance(item, dict) and (item.get("model") or item.get("name"))
        }
    )


def _select_local_model(models: list[str]) -> str | None:
    if not models:
        return None
    for preferred in ("qwen3.5:latest", "qwen3:14b"):
        if preferred in models:
            return preferred
    return models[0]


def _prepare_initial_config() -> dict[str, Any]:
    config = copy.deepcopy(load_config_example())
    for key in list(config):
        if key.startswith("_"):
            config.pop(key)
    providers = config.get("providers", {})
    ollama = providers.get("ollama", {}) if isinstance(providers, dict) else {}
    base_url = str(ollama.get("base_url") or "http://127.0.0.1:11434")
    selected_model = _select_local_model(_discover_ollama_models(base_url))
    if selected_model:
        profiles = config.get("model_profiles", {})
        if isinstance(profiles, dict):
            for profile in profiles.values():
                if isinstance(profile, dict) and profile.get("provider") == "ollama":
                    profile["model"] = selected_model
    return config


def ensure_setup(config_path: str | None = None) -> tuple[Path, bool]:
    """Create the external config once and preserve all later user edits."""
    path = Path(config_path).expanduser() if config_path else get_default_config_path()
    if path.exists():
        return path, False
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, dump_yaml(_prepare_initial_config(), sort_keys=False))
    return path, True


def _run(args: argparse.Namespace) -> int:
    from cli.commands.doctor import main as doctor_main

    path, created = ensure_setup(args.config)
    print(f"config {'created' if created else 'preserved'}: {path}")
    return doctor_main(["--config", str(path)])


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("setup", help="Perform idempotent first-run setup.")
    parser.add_argument("--ensure", action="store_true", help="Create missing config and validate runtime.")
    parser.add_argument("--config", help="Optional external config path.")
    parser.set_defaults(handler=_run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TWR first-run setup.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register(subparsers)
    args = parser.parse_args(["setup", *(argv or [])])
    return int(args.handler(args) or 0)
