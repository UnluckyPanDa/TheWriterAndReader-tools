"""Doctor CLI command."""

from __future__ import annotations

import argparse
from importlib import metadata
from pathlib import Path
import sys
from typing import Any

TOOLS_REPO_ROOT = Path(__file__).resolve().parents[2]


def _python_runtime_issues() -> list[str]:
    issues: list[str] = []
    if sys.version_info < (3, 11):
        issues.append(f"Python 3.11 or newer is required; found {sys.version.split()[0]}")
    try:
        import jsonschema
    except Exception as exc:
        issues.append(f"Python package jsonschema cannot be imported: {exc}")
        return issues
    try:
        version = metadata.version("jsonschema")
    except metadata.PackageNotFoundError:
        issues.append("Python package jsonschema is not installed")
    else:
        try:
            major, minor = (int(part) for part in version.split(".")[:2])
        except ValueError:
            issues.append(f"could not determine jsonschema version: {version}")
        else:
            if (major, minor) < (4, 22):
                issues.append(f"jsonschema 4.22 or newer is required; found {version}")
    return issues


def _configured_ollama_models(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    providers = config.get("providers", {})
    profiles = config.get("model_profiles", {})
    chains = config.get("fallback_chains", {})
    scoped: dict[str, dict[str, Any]] = {}
    if not all(isinstance(item, dict) for item in (providers, profiles, chains)):
        return scoped
    referenced = {
        str(profile_name)
        for chain in chains.values()
        if isinstance(chain, list)
        for profile_name in chain
    }
    for profile_name in sorted(referenced):
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            continue
        provider_name = profile.get("provider")
        provider = providers.get(provider_name)
        command = provider.get("command") if isinstance(provider, dict) else None
        if (
            not isinstance(provider, dict)
            or not provider.get("enabled", False)
            or provider.get("type") != "local_cli"
            or not isinstance(command, str)
            or Path(command).name.lower() != "ollama"
        ):
            continue
        entry = scoped.setdefault(
            str(provider_name),
            {
                "base_url": str(provider.get("base_url") or "http://127.0.0.1:11434"),
                "models": set(),
            },
        )
        model = profile.get("model")
        if isinstance(model, str) and model.strip():
            entry["models"].add(model)
    return scoped


def _ollama_runtime_issues(config: dict[str, Any]) -> list[str]:
    scoped = _configured_ollama_models(config)
    if not scoped:
        return []
    try:
        import requests
    except ImportError:
        return ["Python package requests is not installed; Ollama reachability cannot be checked"]
    issues: list[str] = []
    for provider_name, settings in scoped.items():
        base_url = str(settings["base_url"])
        try:
            response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=3.0)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            message = str(exc)
            lowered = message.lower()
            if any(marker in lowered for marker in ("permission", "operation not permitted", "sandbox")):
                issues.append(
                    f"provider {provider_name}: sandbox denied localhost Ollama access at {base_url}; retry doctor with loopback network approval"
                )
            else:
                issues.append(f"provider {provider_name}: Ollama is unreachable at {base_url}: {message}")
            continue
        models = body.get("models", []) if isinstance(body, dict) else []
        installed = {
            str(item.get("model") or item.get("name"))
            for item in models
            if isinstance(item, dict) and (item.get("model") or item.get("name"))
        }
        for model in sorted(settings["models"]):
            if model not in installed:
                issues.append(
                    f"provider {provider_name}: configured fallback-chain model is not installed: {model}"
                )
    return issues


def _run(args: argparse.Namespace) -> int:
    from shared.lib.codex_cli_runner import validate_codex_runtime
    from shared.lib.config_loader import load_config, validate_config
    from shared.lib.path_rules import assert_tools_repo_has_no_story_content, assert_workspace_has_no_tool_code
    from shared.lib.workspace_loader import validate_workspace_path

    config = load_config(args.config)
    issues = _python_runtime_issues()
    issues.extend(validate_config(config))
    issues.extend(_ollama_runtime_issues(config))
    providers = config.get("providers", {})
    if isinstance(providers, dict):
        for provider_name, provider_config in providers.items():
            if (
                not isinstance(provider_config, dict)
                or provider_config.get("type") != "codex_cli"
                or not provider_config.get("enabled", False)
            ):
                continue
            issues.extend(
                f"provider {provider_name}: {issue}"
                for issue in validate_codex_runtime(provider_config)
            )
    issues.extend(assert_tools_repo_has_no_story_content(TOOLS_REPO_ROOT))
    if args.workspace:
        issues.extend(validate_workspace_path(args.workspace))
        issues.extend(assert_workspace_has_no_tool_code(args.workspace))

    if issues:
        for issue in issues:
            print(f"error: {issue}")
        return 1
    print("doctor ok")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register doctor command."""
    parser = subparsers.add_parser(
        "doctor",
        help="Validate config, provider runtime, and path boundaries.",
    )
    parser.add_argument("--config", help="Optional config path.")
    parser.add_argument("--workspace", help="Optional external story workspace path.")
    parser.set_defaults(handler=_run)


def main(argv: list[str] | None = None) -> int:
    """Run doctor directly."""
    parser = argparse.ArgumentParser(description="Doctor command.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register(subparsers)
    args = parser.parse_args(["doctor", *(argv or [])])
    return int(args.handler(args) or 0)
