"""Run isolated, schema-constrained Codex CLI review sessions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Any


REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}


def codex_home(provider_config: dict[str, Any] | None = None) -> Path:
    """Return the configured isolated CODEX_HOME without reading authentication data."""
    if provider_config is not None:
        configured = provider_config.get("codex_home")
        if not isinstance(configured, str) or not configured.strip():
            raise ValueError("codex_cli provider requires a dedicated codex_home")
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise ValueError("codex_cli provider codex_home must be an absolute path")
        return path.resolve(strict=False)
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def codex_profile_path(profile: str, home: str | Path | None = None) -> Path:
    """Resolve an official Codex profile name to its config file."""
    root = Path(home).expanduser() if home is not None else codex_home()
    return root / f"{profile}.config.toml"


def validate_codex_profile(profile: str, home: str | Path | None = None) -> list[str]:
    """Validate the dedicated review profile's local isolation contract."""
    root = Path(home).expanduser() if home is not None else codex_home()
    path = codex_profile_path(profile, root)
    if not path.is_file():
        return [f"Codex review profile is missing: {path}"]
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"Codex review profile is invalid: {path}: {exc}"]

    issues: list[str] = []
    required = {
        "approval_policy": "never",
        "sandbox_mode": "read-only",
        "web_search": "disabled",
    }
    for key, expected in required.items():
        if data.get(key) != expected:
            issues.append(f"Codex review profile {profile} requires {key} = {expected!r}")
    instructions = data.get("developer_instructions")
    if not isinstance(instructions, str) or not instructions.strip():
        issues.append(f"Codex review profile {profile} requires non-empty developer_instructions")
    environment_policy = data.get("shell_environment_policy")
    if not isinstance(environment_policy, dict) or environment_policy.get("inherit") != "none":
        issues.append(
            f"Codex review profile {profile} requires shell_environment_policy.inherit = 'none'"
        )
    features = data.get("features")
    for feature in ("apps", "goals", "hooks", "memories", "multi_agent", "shell_tool"):
        if not isinstance(features, dict) or features.get(feature) is not False:
            issues.append(f"Codex review profile {profile} requires features.{feature} = false")
    for filename in ("AGENTS.override.md", "AGENTS.md"):
        instruction_path = root / filename
        if instruction_path.exists():
            issues.append(
                f"Dedicated Codex review home must not contain instruction file: {instruction_path}"
            )
    return issues


def validate_codex_runtime(provider_config: dict[str, Any]) -> list[str]:
    """Check an enabled Codex executable, dedicated profile, and saved login."""
    if not provider_config.get("enabled", False):
        return []
    command = provider_config.get("command", "codex")
    profile = provider_config.get("profile")
    issues: list[str] = []
    if not isinstance(command, str) or not command.strip() or shutil.which(command) is None:
        issues.append(f"Codex review command was not found: {command}")
        return issues
    if not isinstance(profile, str) or not profile.strip():
        issues.append("Codex CLI provider requires a dedicated profile")
        return issues
    try:
        home = codex_home(provider_config)
    except ValueError as exc:
        issues.append(str(exc))
        return issues
    issues.extend(validate_codex_profile(profile, home))
    environment = {**os.environ, "CODEX_HOME": str(home)}
    try:
        completed = subprocess.run(
            [command, "login", "status"],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        issues.append(f"Codex login status could not be checked: {exc}")
    else:
        if completed.returncode != 0:
            reason = completed.stderr.strip() or completed.stdout.strip() or "not logged in"
            issues.append(f"Codex authentication is unavailable: {reason}")
    return issues


def _session_settings(provider_config: dict[str, Any]) -> tuple[str, str]:
    session = provider_config.get("session", {})
    if not isinstance(session, dict):
        raise ValueError("codex_cli provider session must be a mapping")
    start_mode = session.get("start_mode")
    retention = session.get("retention")
    if start_mode != "fresh":
        raise ValueError("codex_cli review only supports session.start_mode fresh")
    if retention not in {"persisted", "ephemeral"}:
        raise ValueError("codex_cli provider session.retention must be persisted or ephemeral")
    return str(start_mode), str(retention)


def build_codex_command(
    provider_config: dict[str, Any],
    model_profile: dict[str, Any],
    output_schema_path: str | Path,
    working_directory: str | Path,
) -> list[str]:
    """Build a fresh, read-only Codex exec command for one reviewer."""
    command = provider_config.get("command", "codex")
    profile = provider_config.get("profile")
    model = model_profile.get("model")
    effort = model_profile.get("reasoning_effort")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("codex_cli provider requires a non-empty command")
    if not isinstance(profile, str) or not profile.strip():
        raise ValueError("codex_cli provider requires a dedicated profile")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("resolved Codex reviewer model is missing")
    if effort not in REASONING_EFFORTS:
        raise ValueError("resolved Codex reviewer reasoning_effort is invalid")
    _, retention = _session_settings(provider_config)
    schema_path = Path(output_schema_path).expanduser().resolve(strict=False)
    if not schema_path.is_file():
        raise ValueError(f"Codex output schema is missing: {schema_path}")

    args = [
        command,
        "exec",
        "--profile",
        profile,
        "--strict-config",
        "--ignore-user-config",
        "--ignore-rules",
        "--json",
        "--color",
        "never",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--output-schema",
        str(schema_path),
        "--model",
        model,
        "-c",
        f'model_reasoning_effort="{effort}"',
        "-c",
        'approval_policy="never"',
        "-c",
        'web_search="disabled"',
        "-C",
        str(Path(working_directory).resolve(strict=False)),
    ]
    if retention == "ephemeral":
        args.append("--ephemeral")
    args.append("-")
    return args


def parse_codex_jsonl(text: str) -> dict[str, Any]:
    """Extract the thread, final agent message, and usage from Codex JSONL."""
    thread_id: str | None = None
    final_message: str | None = None
    usage: dict[str, int] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid Codex JSONL at line {line_number}: {exc.msg}") from exc
        if not isinstance(event, dict):
            raise ValueError(f"invalid Codex JSONL event at line {line_number}")
        event_type = event.get("type")
        if event_type == "thread.started":
            value = event.get("thread_id")
            if isinstance(value, str) and value.strip():
                thread_id = value
        elif event_type == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                value = item.get("text")
                if isinstance(value, str) and value.strip():
                    final_message = value
        elif event_type == "turn.completed":
            value = event.get("usage")
            if isinstance(value, dict):
                usage = {
                    str(key): int(item)
                    for key, item in value.items()
                    if isinstance(item, int) and item >= 0
                }
        elif event_type in {"error", "turn.failed"}:
            message = event.get("message") or event.get("error") or event_type
            raise ValueError(f"Codex run failed: {message}")
    if not thread_id:
        raise ValueError("Codex JSONL did not contain thread.started")
    if not final_message:
        raise ValueError("Codex JSONL did not contain a final agent message")
    return {"thread_id": thread_id, "text": final_message, "usage": usage}


def run_codex_cli_model(
    provider_config: dict[str, Any],
    model_profile: dict[str, Any],
    prompt: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one prompt in a new persisted or ephemeral Codex review thread."""
    options = options or {}
    profile = provider_config.get("profile")
    try:
        home = codex_home(provider_config)
    except ValueError as exc:
        return {"ok": False, "text": "", "reason": str(exc)}
    if not isinstance(profile, str) or validate_codex_profile(profile, home):
        return {"ok": False, "text": "", "reason": "codex_profile_missing_or_invalid"}
    command = provider_config.get("command", "codex")
    if not isinstance(command, str) or shutil.which(command) is None:
        return {"ok": False, "text": "", "reason": "command_not_found"}
    output_schema_path = options.get("output_schema_path")
    if not output_schema_path:
        return {"ok": False, "text": "", "reason": "output_schema_path_required"}
    try:
        start_mode, retention = _session_settings(provider_config)
    except ValueError as exc:
        return {"ok": False, "text": "", "reason": str(exc)}

    timeout = options.get("timeout_seconds", provider_config.get("timeout_seconds", 900))
    environment = {**os.environ, "CODEX_HOME": str(home)}
    with tempfile.TemporaryDirectory(prefix="twr-codex-review-") as temp_dir:
        try:
            args = build_codex_command(provider_config, model_profile, output_schema_path, temp_dir)
            completed = subprocess.run(
                args,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=float(timeout),
                check=False,
                env=environment,
            )
        except ValueError as exc:
            return {"ok": False, "text": "", "reason": str(exc)}
        except subprocess.TimeoutExpired:
            return {"ok": False, "text": "", "reason": "timeout"}
        except OSError as exc:
            return {"ok": False, "text": "", "reason": f"execution_failed: {exc}"}

    if completed.returncode != 0:
        reason = completed.stderr.strip() or f"exit_code_{completed.returncode}"
        return {"ok": False, "text": completed.stdout.strip(), "reason": reason}
    try:
        parsed = parse_codex_jsonl(completed.stdout)
    except ValueError as exc:
        return {"ok": False, "text": "", "reason": str(exc)}
    return {
        "ok": True,
        "text": parsed["text"],
        "reason": None,
        "model": model_profile.get("model"),
        "reasoning_effort": model_profile.get("reasoning_effort"),
        "codex_profile": profile,
        "requested_intelligence": model_profile.get("requested_intelligence"),
        "resolved_intelligence": model_profile.get("resolved_intelligence"),
        "session": {
            "start_mode": start_mode,
            "retention": retention,
            "thread_id": parsed["thread_id"],
            "resumed_from": None,
        },
        "usage": parsed["usage"],
    }
