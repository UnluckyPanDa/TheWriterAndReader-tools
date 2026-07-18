from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import requests

from shared.lib.config_loader import load_config
from shared.lib.ollama_check import get_ollama_models


REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_SECONDS = 900.0
DEFAULT_DISCOVERY_TIMEOUT_SECONDS = 10.0
DEFAULT_CONTEXT_PROBE_TIMEOUT_SECONDS = 30.0
DEFAULT_NUM_CTX = 32768

_CONTEXT_KEY_RE = re.compile(
    r"(context|ctx|num_ctx|context_length|context_window|max_context)",
    re.IGNORECASE,
)
_CONTEXT_TEXT_RE = re.compile(
    r"(num_ctx|context[_ -]?length|context[_ -]?window|max[_ -]?context[_ -]?length)\D{0,30}(\d{4,7})",
    re.IGNORECASE,
)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _configured_ollama(config: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    providers = config.get("providers", {})
    profiles = config.get("model_profiles", {})
    if not isinstance(providers, dict) or not isinstance(profiles, dict):
        return {}, []
    for provider_name, provider in providers.items():
        command = provider.get("command") if isinstance(provider, dict) else None
        if (
            isinstance(provider, dict)
            and provider.get("enabled", False)
            and provider.get("type") == "local_cli"
            and isinstance(command, str)
            and Path(command).name.lower() == "ollama"
        ):
            models = [
                str(profile["model"])
                for profile in profiles.values()
                if isinstance(profile, dict)
                and profile.get("provider") == provider_name
                and isinstance(profile.get("model"), str)
            ]
            return provider, models
    return {}, []


def _extract_context_length(value: Any, key_path: str = "") -> int | None:
    candidates: list[int] = []

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{key_path}.{key}" if key_path else str(key)
            child_limit = _extract_context_length(child, child_path)
            if child_limit is not None:
                candidates.append(child_limit)
        return max(candidates) if candidates else None

    if isinstance(value, list):
        for index, child in enumerate(value):
            child_limit = _extract_context_length(child, f"{key_path}[{index}]")
            if child_limit is not None:
                candidates.append(child_limit)
        return max(candidates) if candidates else None

    key_mentions_context = bool(_CONTEXT_KEY_RE.search(key_path))
    if isinstance(value, int) and key_mentions_context:
        candidates.append(value)

    if isinstance(value, str):
        for match in _CONTEXT_TEXT_RE.finditer(value):
            candidates.append(int(match.group(2)))
        if key_mentions_context:
            for match in re.finditer(r"\b(\d{4,7})\b", value):
                candidates.append(int(match.group(1)))

    return max(candidates) if candidates else None


def inspect_model_context(
    base_url: str,
    model: str,
    timeout: float = DEFAULT_CONTEXT_PROBE_TIMEOUT_SECONDS,
) -> tuple[int | None, list[str]]:
    diagnostics: list[str] = []
    url = f"{base_url.rstrip('/')}/api/show"

    try:
        response = requests.post(url, json={"model": model}, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        context_limit = _extract_context_length(data)
        if context_limit is not None:
            diagnostics.append(f"HTTP /api/show context limit: {context_limit}")
            return context_limit, diagnostics
        diagnostics.append("HTTP /api/show did not expose a context limit.")
    except Exception as exc:
        diagnostics.append(f"HTTP /api/show context probe failed: {exc}")

    ollama_cli = shutil.which("ollama")
    if not ollama_cli:
        diagnostics.append("ollama CLI not found for context probe.")
        return None, diagnostics

    try:
        result = subprocess.run(
            [ollama_cli, "show", model, "--json"],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            diagnostics.append(f"ollama show --json failed: {result.stderr.strip() or result.returncode}")
            return None, diagnostics
        data = json.loads(result.stdout)
        context_limit = _extract_context_length(data)
        if context_limit is not None:
            diagnostics.append(f"ollama show --json context limit: {context_limit}")
            return context_limit, diagnostics
        diagnostics.append("ollama show --json did not expose a context limit.")
    except Exception as exc:
        diagnostics.append(f"ollama show --json context probe failed: {exc}")

    return None, diagnostics


def select_ollama_model(
    role: str,
    repo_root: Path = REPO_ROOT,
    requested_model: str | None = None,
    interactive: bool | None = None,
) -> str | None:
    del role, repo_root
    config = load_config()
    settings, configured_models = _configured_ollama(config)
    base_url = settings.get("base_url", DEFAULT_BASE_URL)
    discovery_timeout = _as_float(
        settings.get("discovery_timeout_seconds"),
        DEFAULT_DISCOVERY_TIMEOUT_SECONDS,
    )
    reachable, installed, error = get_ollama_models(base_url, timeout=discovery_timeout)
    default_model = next((name for name in configured_models if name in installed), None)
    if default_model is None:
        default_model = configured_models[0] if configured_models else (installed[0] if installed else None)

    if reachable and installed:
        installed = sorted(installed)

    if requested_model:
        if reachable and installed and requested_model not in installed:
            print(f"WARNING: Requested model `{requested_model}` is not installed locally.", file=sys.stderr)
        return requested_model

    can_prompt = sys.stdin.isatty() and sys.stdout.isatty()
    if interactive is None:
        interactive = can_prompt
    else:
        interactive = bool(interactive) and can_prompt

    if not interactive:
        return default_model

    if not reachable:
        print(f"WARNING: Ollama model discovery failed: {error}", file=sys.stderr)
        return default_model

    if not installed:
        print("WARNING: No installed Ollama models found.", file=sys.stderr)
        return default_model

    print("Installed Ollama models:")
    for index, name in enumerate(installed, start=1):
        marker = " (default)" if name == default_model else ""
        print(f"{index}. {name}{marker}")

    choice = input("Select Ollama model [Enter for default]: ").strip()
    if not choice:
        return default_model
    if choice.isdigit():
        selected_index = int(choice) - 1
        if 0 <= selected_index < len(installed):
            return installed[selected_index]
    if choice in installed:
        return choice

    print(f"WARNING: Unknown model selection `{choice}`; using default.", file=sys.stderr)
    return default_model


def _http_generate(
    base_url: str,
    model: str,
    prompt: str,
    options: dict[str, Any],
    timeout: float,
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": options,
    }
    response = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(data["error"])
    text = (data.get("response") or "").strip()
    if not text:
        raise RuntimeError("Ollama HTTP returned a blank/null response.")
    return text


def call_ollama(
    prompt: str,
    role: str = "reviewer",
    repo_root: Path = REPO_ROOT,
    model: str | None = None,
    requested_model: str | None = None,
    interactive: bool = False,
    temperature: float = 0.2,
    num_predict: int | None = None,
) -> str:
    del repo_root
    config = load_config()
    settings, configured_models = _configured_ollama(config)
    base_url = settings.get("base_url", DEFAULT_BASE_URL)
    timeout = _as_float(settings.get("timeout_seconds"), DEFAULT_TIMEOUT_SECONDS)
    context_probe_timeout = _as_float(
        settings.get("context_probe_timeout_seconds"),
        DEFAULT_CONTEXT_PROBE_TIMEOUT_SECONDS,
    )
    configured_num_ctx = _as_int(settings.get("num_ctx"), DEFAULT_NUM_CTX)
    selected_model = model or requested_model
    if selected_model is None:
        reachable, installed, _ = get_ollama_models(base_url, timeout=DEFAULT_DISCOVERY_TIMEOUT_SECONDS)
        selected_model = next((name for name in configured_models if not reachable or name in installed), None)
        if selected_model is None and reachable and installed:
            selected_model = installed[0]

    diagnostics: list[str] = []
    if not selected_model:
        raise RuntimeError("No local Ollama model could be selected.")

    context_limit, context_diagnostics = inspect_model_context(
        base_url,
        selected_model,
        timeout=context_probe_timeout,
    )
    diagnostics.extend(context_diagnostics)
    effective_num_ctx = min(configured_num_ctx, context_limit) if context_limit else configured_num_ctx
    estimated_prompt_tokens = max(1, len(prompt) // 4)
    diagnostics.append(f"Configured num_ctx: {configured_num_ctx}")
    diagnostics.append(f"Effective num_ctx: {effective_num_ctx}")
    diagnostics.append(f"Estimated prompt tokens: {estimated_prompt_tokens}")

    if estimated_prompt_tokens >= effective_num_ctx:
        raise RuntimeError("Prompt is likely larger than the available local model context; reduce context before generation.")

    options: dict[str, Any] = {
        "temperature": temperature,
        "num_ctx": effective_num_ctx,
    }
    if num_predict is not None:
        options["num_predict"] = num_predict

    try:
        return _http_generate(base_url, selected_model, prompt, options, timeout)
    except Exception as exc:
        detail = "; ".join(diagnostics[-3:])
        raise RuntimeError(f"Ollama HTTP generation failed: {exc}. {detail}") from exc
