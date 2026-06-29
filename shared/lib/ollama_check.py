from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import requests
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "models.yaml"


def load_models_config(path: Path | str = DEFAULT_CONFIG) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def get_ollama_models(base_url: str, timeout: float = 2.0) -> tuple[bool, list[str], str | None]:
    try:
        response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - doctor should report any local connectivity issue.
        return False, [], str(exc)

    data = response.json()
    names = sorted(model.get("name", "") for model in data.get("models", []) if model.get("name"))
    return True, names, None


def _norm(value: str) -> str:
    return value.lower().replace("-", "").replace("_", "").replace(" ", "")


def closest_model(role: str, config: dict[str, Any], installed: list[str]) -> str | None:
    role_config = (config.get("models") or {}).get(role) or {}
    preferred = role_config.get("preferred")
    fallback = role_config.get("fallback")
    installed_norm = {_norm(name): name for name in installed}

    for candidate in (preferred, fallback):
        if candidate and _norm(candidate) in installed_norm:
            return installed_norm[_norm(candidate)]

    targets: list[str] = []
    for candidate in (preferred, fallback):
        if candidate:
            candidate_norm = _norm(candidate)
            if "14b" in candidate_norm:
                targets.append("14b")
            if "8b" in candidate_norm:
                targets.append("8b")

    qwen = [name for name in installed if "qwen3" in _norm(name)]
    for target in targets:
        for name in qwen:
            if target in _norm(name):
                return name
    return qwen[0] if qwen else (installed[0] if installed else None)


def missing_model_warnings(config: dict[str, Any], installed: list[str]) -> list[str]:
    warnings: list[str] = []
    installed_norm = {_norm(name) for name in installed}
    for role, role_config in (config.get("models") or {}).items():
        preferred = role_config.get("preferred")
        fallback = role_config.get("fallback")
        if preferred and _norm(preferred) not in installed_norm:
            warnings.append(f"{role} preferred model missing: {preferred}")
        if fallback and _norm(fallback) not in installed_norm:
            warnings.append(f"{role} fallback model missing: {fallback}")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local Ollama models.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()

    config = load_models_config(args.config)
    base_url = (config.get("ollama") or {}).get("base_url", "http://localhost:11434")
    reachable, models, error = get_ollama_models(base_url)
    print(f"Ollama base URL: {base_url}")
    print(f"Reachable: {'yes' if reachable else 'no'}")
    if error:
        print(f"Error: {error}")
    print("Installed models:")
    for model in models:
        print(f"- {model}")
    if not models:
        print("- none detected")
    for warning in missing_model_warnings(config, models):
        print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
