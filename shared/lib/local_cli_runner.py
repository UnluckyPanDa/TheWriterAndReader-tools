"""Run local command-line model providers."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any


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
