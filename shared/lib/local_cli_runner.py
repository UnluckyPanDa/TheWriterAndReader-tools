"""Run local model providers, routing Ollama through its native HTTP API."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

import requests


DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"


def _is_ollama_provider(provider_config: dict[str, Any]) -> bool:
    command = provider_config.get("command")
    return isinstance(command, str) and Path(command).name.lower() == "ollama"


def _load_output_schema(options: dict[str, Any]) -> dict[str, Any]:
    schema_path = options.get("output_schema_path")
    if not isinstance(schema_path, (str, Path)):
        raise ValueError("output_schema_path_required")
    path = Path(schema_path).expanduser().resolve(strict=False)
    if not path.is_file():
        raise ValueError(f"output_schema_missing: {path}")
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"output_schema_invalid: {exc}") from exc
    if not isinstance(schema, dict):
        raise ValueError("output_schema_must_be_object")
    return schema


def _run_ollama_http_model(
    provider_config: dict[str, Any],
    model_profile: dict[str, Any],
    prompt: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    model = model_profile.get("model")
    if not isinstance(model, str) or not model.strip():
        return {"ok": False, "text": "", "reason": "missing_model"}
    structured_output = options.get("structured_output", False)
    if not isinstance(structured_output, bool):
        return {"ok": False, "text": "", "reason": "structured_output_must_be_boolean"}

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
    }
    generation_options: dict[str, Any] = {}
    for option_name in ("temperature", "num_ctx", "num_predict", "seed"):
        if option_name in options:
            generation_options[option_name] = options[option_name]
    if generation_options:
        payload["options"] = generation_options
    if structured_output:
        try:
            payload["format"] = _load_output_schema(options)
        except ValueError as exc:
            return {"ok": False, "text": "", "reason": str(exc)}

    base_url = str(provider_config.get("base_url") or DEFAULT_OLLAMA_BASE_URL)
    timeout = float(options.get("timeout_seconds", provider_config.get("timeout_seconds", 600)))
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/api/generate",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        body = response.json()
    except requests.Timeout:
        return {"ok": False, "text": "", "reason": "timeout"}
    except requests.RequestException as exc:
        message = str(exc)
        lowered = message.lower()
        denied = any(marker in lowered for marker in ("permission", "operation not permitted", "sandbox"))
        reason = "localhost_access_denied" if denied else f"request_failed: {message}"
        return {"ok": False, "text": "", "reason": reason}
    except (TypeError, ValueError) as exc:
        return {"ok": False, "text": "", "reason": f"invalid_response: {exc}"}

    if not isinstance(body, dict):
        return {"ok": False, "text": "", "reason": "invalid_response_shape"}
    if body.get("error"):
        return {"ok": False, "text": "", "reason": str(body["error"])}
    text = body.get("response")
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "text": "", "reason": "empty_response"}
    return {"ok": True, "text": text.strip(), "reason": None, "model": model}


def build_cli_command(provider_config: dict[str, Any], model_profile: dict[str, Any]) -> list[str]:
    """Build the local CLI command for a model profile."""
    command = provider_config.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("local_cli provider is missing a non-empty 'command'")

    model = model_profile.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model profile is missing a non-empty 'model'")

    run_args = provider_config.get("run_args", [])
    if run_args is None:
        run_args = []
    if not isinstance(run_args, list) or not all(isinstance(item, str) for item in run_args):
        raise ValueError("local_cli provider 'run_args' must be a list of strings")

    return [command, *[arg.replace("{model}", model) for arg in run_args]]


def run_local_cli_model(
    provider_config: dict[str, Any],
    model_profile: dict[str, Any],
    prompt: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a prompt through a configured local CLI model provider."""
    options = options or {}
    if _is_ollama_provider(provider_config):
        return _run_ollama_http_model(provider_config, model_profile, prompt, options)
    try:
        command = build_cli_command(provider_config, model_profile)
    except ValueError as exc:
        return {"ok": False, "text": "", "reason": str(exc)}

    executable = command[0]
    if shutil.which(executable) is None:
        return {"ok": False, "text": "", "reason": "command_not_found"}

    timeout = options.get("timeout_seconds", provider_config.get("timeout_seconds", 600))
    stdin_prompt = bool(provider_config.get("stdin_prompt", True))
    input_text = prompt if stdin_prompt else None
    if not stdin_prompt:
        command = [*command, prompt]

    try:
        completed = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=float(timeout),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "text": "", "reason": "timeout"}
    except OSError as exc:
        return {"ok": False, "text": "", "reason": f"execution_failed: {exc}"}

    if completed.returncode != 0:
        reason = completed.stderr.strip() or f"exit_code_{completed.returncode}"
        return {"ok": False, "text": completed.stdout.strip(), "reason": reason}

    return {"ok": True, "text": completed.stdout.strip(), "reason": None}
