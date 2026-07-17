"""Run isolated Codex CLI writing and review sessions."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Any


REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}
CODEX_CAPABILITIES = {"review", "writing"}
AGENT_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def _provider_capability(provider_config: dict[str, Any]) -> str:
    capability = provider_config.get("capability", "review")
    if capability not in CODEX_CAPABILITIES:
        raise ValueError("codex_cli provider capability must be review or writing")
    return str(capability)


def _subagent_settings(provider_config: dict[str, Any]) -> tuple[bool, int, str | None]:
    settings = provider_config.get("subagents")
    if settings is None:
        return False, 0, None
    if not isinstance(settings, dict):
        raise ValueError("codex_cli provider subagents must be a mapping")
    required = settings.get("required", False)
    if not isinstance(required, bool):
        raise ValueError("codex_cli provider subagents.required must be a boolean")
    if not required:
        return False, 0, None
    if _provider_capability(provider_config) != "review":
        raise ValueError("codex_cli writing providers cannot require review subagents")
    count = settings.get("count")
    if type(count) is not int or count != 1:
        raise ValueError("codex_cli review subagents.count must be exactly 1")
    agent = settings.get("agent")
    if not isinstance(agent, str) or not AGENT_NAME.fullmatch(agent):
        raise ValueError("codex_cli review subagents.agent must be a safe agent name")
    return True, 1, agent


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


def _validate_subagent_profile(root: Path, agent_name: str) -> list[str]:
    path = root / "agents" / f"{agent_name}.toml"
    if not path.is_file():
        return [f"Codex review subagent profile is missing: {path}"]
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"Codex review subagent profile is invalid: {path}: {exc}"]

    issues: list[str] = []
    for field in ("name", "description", "developer_instructions"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append(f"Codex review subagent {agent_name} requires non-empty {field}")
    if data.get("name") != agent_name:
        issues.append(f"Codex review subagent profile name must be {agent_name!r}")
    for key, expected in (
        ("approval_policy", "never"),
        ("sandbox_mode", "read-only"),
        ("web_search", "disabled"),
    ):
        if data.get(key) != expected:
            issues.append(f"Codex review subagent {agent_name} requires {key} = {expected!r}")
    environment_policy = data.get("shell_environment_policy")
    if not isinstance(environment_policy, dict) or environment_policy.get("inherit") != "none":
        issues.append(
            f"Codex review subagent {agent_name} requires shell_environment_policy.inherit = 'none'"
        )
    features = data.get("features")
    for feature in ("apps", "goals", "hooks", "memories", "multi_agent", "plugins", "shell_tool"):
        if not isinstance(features, dict) or features.get(feature) is not False:
            issues.append(f"Codex review subagent {agent_name} requires features.{feature} = false")
    return issues


def validate_codex_profile(
    profile: str,
    home: str | Path | None = None,
    provider_config: dict[str, Any] | None = None,
) -> list[str]:
    """Validate a dedicated profile's capability and isolation contract."""
    root = Path(home).expanduser() if home is not None else codex_home()
    path = codex_profile_path(profile, root)
    if not path.is_file():
        return [f"Codex profile is missing: {path}"]
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"Codex profile is invalid: {path}: {exc}"]

    provider_config = provider_config or {}
    try:
        capability = _provider_capability(provider_config)
        require_subagent, subagent_count, agent_name = _subagent_settings(provider_config)
    except ValueError as exc:
        return [str(exc)]

    issues: list[str] = []
    required = {
        "approval_policy": "never",
        "sandbox_mode": "read-only",
        "web_search": "disabled",
    }
    for key, expected in required.items():
        if data.get(key) != expected:
            issues.append(f"Codex {capability} profile {profile} requires {key} = {expected!r}")
    instructions = data.get("developer_instructions")
    if not isinstance(instructions, str) or not instructions.strip():
        issues.append(f"Codex {capability} profile {profile} requires non-empty developer_instructions")
    environment_policy = data.get("shell_environment_policy")
    if not isinstance(environment_policy, dict) or environment_policy.get("inherit") != "none":
        issues.append(
            f"Codex {capability} profile {profile} requires shell_environment_policy.inherit = 'none'"
        )
    features = data.get("features")
    for feature in ("apps", "goals", "hooks", "memories", "plugins", "shell_tool"):
        if not isinstance(features, dict) or features.get(feature) is not False:
            issues.append(f"Codex {capability} profile {profile} requires features.{feature} = false")
    expected_multi_agent = capability == "review" and require_subagent
    if not isinstance(features, dict) or features.get("multi_agent") is not expected_multi_agent:
        issues.append(
            f"Codex {capability} profile {profile} requires features.multi_agent = "
            f"{str(expected_multi_agent).lower()}"
        )
    if require_subagent:
        agents = data.get("agents")
        if not isinstance(agents, dict):
            issues.append(f"Codex review profile {profile} requires an agents table")
        else:
            if agents.get("max_threads") != subagent_count + 1:
                issues.append(
                    f"Codex review profile {profile} requires agents.max_threads = {subagent_count + 1}"
                )
            if agents.get("max_depth") != 1:
                issues.append(f"Codex review profile {profile} requires agents.max_depth = 1")
            if agents.get("interrupt_message") is not False:
                issues.append(f"Codex review profile {profile} requires agents.interrupt_message = false")
        if agent_name is not None:
            issues.extend(_validate_subagent_profile(root, agent_name))
    for filename in ("AGENTS.override.md", "AGENTS.md"):
        instruction_path = root / filename
        if instruction_path.exists():
            issues.append(
                f"Dedicated Codex home must not contain instruction file: {instruction_path}"
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
        issues.append(f"Codex command was not found: {command}")
        return issues
    if not isinstance(profile, str) or not profile.strip():
        issues.append("Codex CLI provider requires a dedicated profile")
        return issues
    try:
        home = codex_home(provider_config)
    except ValueError as exc:
        issues.append(str(exc))
        return issues
    issues.extend(validate_codex_profile(profile, home, provider_config))
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
        raise ValueError("codex_cli only supports session.start_mode fresh")
    if retention not in {"persisted", "ephemeral"}:
        raise ValueError("codex_cli provider session.retention must be persisted or ephemeral")
    return str(start_mode), str(retention)


def build_codex_command(
    provider_config: dict[str, Any],
    model_profile: dict[str, Any],
    output_schema_path: str | Path | None,
    working_directory: str | Path,
) -> list[str]:
    """Build a fresh, read-only Codex exec command."""
    command = provider_config.get("command", "codex")
    profile = provider_config.get("profile")
    model = model_profile.get("model")
    effort = model_profile.get("reasoning_effort")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("codex_cli provider requires a non-empty command")
    if not isinstance(profile, str) or not profile.strip():
        raise ValueError("codex_cli provider requires a dedicated profile")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("resolved Codex model is missing")
    if effort not in REASONING_EFFORTS:
        raise ValueError("resolved Codex reasoning_effort is invalid")
    capability = _provider_capability(provider_config)
    _, retention = _session_settings(provider_config)
    schema_path: Path | None = None
    if output_schema_path is not None:
        schema_path = Path(output_schema_path).expanduser().resolve(strict=False)
        if not schema_path.is_file():
            raise ValueError(f"Codex output schema is missing: {schema_path}")
    elif capability == "review":
        raise ValueError("codex_cli review requires output_schema_path")

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
    if schema_path is not None:
        insertion = args.index("--model")
        args[insertion:insertion] = ["--output-schema", str(schema_path)]
    if retention == "ephemeral":
        args.append("--ephemeral")
    args.append("-")
    return args


def parse_codex_jsonl(text: str, require_delegation: bool = False) -> dict[str, Any]:
    """Extract output and verify any required Codex-native delegation."""
    thread_id: str | None = None
    final_message: str | None = None
    final_message_index: int | None = None
    usage: dict[str, int] = {}
    spawned: list[tuple[str, int]] = []
    completed: dict[str, int] = {}
    for event_index, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid Codex JSONL at line {event_index}: {exc.msg}") from exc
        if not isinstance(event, dict):
            raise ValueError(f"invalid Codex JSONL event at line {event_index}")
        event_type = event.get("type")
        if event_type == "thread.started":
            value = event.get("thread_id")
            if thread_id is None and isinstance(value, str) and value.strip():
                thread_id = value
        elif event_type == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                value = item.get("text")
                if isinstance(value, str) and value.strip():
                    final_message = value
                    final_message_index = event_index
            elif isinstance(item, dict) and item.get("type") == "collab_tool_call":
                tool = item.get("tool")
                status = item.get("status")
                sender = item.get("sender_thread_id")
                receivers = item.get("receiver_thread_ids")
                receiver_ids = (
                    [value for value in receivers if isinstance(value, str) and value.strip()]
                    if isinstance(receivers, list)
                    else []
                )
                spawn_prompt = item.get("prompt")
                if (
                    status == "completed"
                    and sender == thread_id
                    and tool == "spawn_agent"
                    and isinstance(spawn_prompt, str)
                    and spawn_prompt.strip()
                ):
                    spawned.extend((value, event_index) for value in receiver_ids if value != thread_id)
                elif status == "completed" and sender == thread_id and tool == "wait":
                    states = item.get("agents_states")
                    if isinstance(states, dict):
                        for child_id, state in states.items():
                            if (
                                isinstance(child_id, str)
                                and isinstance(state, dict)
                                and state.get("status") == "completed"
                                and isinstance(state.get("message"), str)
                                and state["message"].strip()
                                and (not receiver_ids or child_id in receiver_ids)
                            ):
                                completed[child_id] = event_index
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
    delegation: dict[str, Any] | None = None
    if require_delegation:
        spawned_ids = [child_id for child_id, _ in spawned]
        if len(spawned_ids) != 1 or len(set(spawned_ids)) != 1:
            raise ValueError("Codex review requires exactly one completed subagent spawn")
        child_id = spawned_ids[0]
        spawn_index = spawned[0][1]
        wait_index = completed.get(child_id)
        if wait_index is None or wait_index <= spawn_index:
            raise ValueError("Codex review subagent did not complete through a later wait")
        if final_message_index is None or final_message_index <= wait_index:
            raise ValueError("Codex review final response preceded subagent completion")
        delegation = {
            "mode": "codex_native",
            "required": True,
            "spawned_thread_ids": [child_id],
            "completed_thread_ids": [child_id],
        }
    return {
        "thread_id": thread_id,
        "text": final_message,
        "usage": usage,
        "delegation": delegation,
    }


def _delegated_review_prompt(prompt: str, agent_name: str) -> str:
    return f"""Complete this review through exactly one Codex subagent.

1. Spawn exactly one direct child using the custom agent type `{agent_name}`.
2. Give that child the complete review assignment and all supplied evidence below.
3. Wait for the child to finish. Do not answer before its result is available.
4. Use the child's evidence, apply your own judgment, and return only the required final JSON object.
5. Do not spawn any additional child and do not delegate recursively.

## Complete Review Assignment
{prompt}
"""


def run_codex_cli_model(
    provider_config: dict[str, Any],
    model_profile: dict[str, Any],
    prompt: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one prompt in a new persisted or ephemeral Codex thread."""
    options = options or {}
    profile = provider_config.get("profile")
    try:
        home = codex_home(provider_config)
    except ValueError as exc:
        return {"ok": False, "text": "", "reason": str(exc)}
    if not isinstance(profile, str) or validate_codex_profile(profile, home, provider_config):
        return {"ok": False, "text": "", "reason": "codex_profile_missing_or_invalid"}
    command = provider_config.get("command", "codex")
    if not isinstance(command, str) or shutil.which(command) is None:
        return {"ok": False, "text": "", "reason": "command_not_found"}
    output_schema_path = options.get("output_schema_path")
    try:
        capability = _provider_capability(provider_config)
        require_subagent, _, agent_name = _subagent_settings(provider_config)
        start_mode, retention = _session_settings(provider_config)
    except ValueError as exc:
        return {"ok": False, "text": "", "reason": str(exc)}
    structured_output = options.get("structured_output", False)
    if capability == "writing":
        if not isinstance(structured_output, bool):
            return {"ok": False, "text": "", "reason": "structured_output_must_be_boolean"}
        if not structured_output:
            output_schema_path = None
        elif not output_schema_path:
            return {"ok": False, "text": "", "reason": "output_schema_path_required"}
    if capability == "review" and not output_schema_path:
        return {"ok": False, "text": "", "reason": "output_schema_path_required"}
    effective_prompt = (
        _delegated_review_prompt(prompt, str(agent_name))
        if require_subagent and agent_name is not None
        else prompt
    )

    timeout = options.get("timeout_seconds", provider_config.get("timeout_seconds", 900))
    environment = {**os.environ, "CODEX_HOME": str(home)}
    with tempfile.TemporaryDirectory(prefix=f"twr-codex-{capability}-") as temp_dir:
        try:
            args = build_codex_command(provider_config, model_profile, output_schema_path, temp_dir)
            completed = subprocess.run(
                args,
                input=effective_prompt,
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
        parsed = parse_codex_jsonl(completed.stdout, require_delegation=require_subagent)
    except ValueError as exc:
        return {"ok": False, "text": "", "reason": str(exc)}
    session: dict[str, Any] = {
        "start_mode": start_mode,
        "retention": retention,
        "thread_id": parsed["thread_id"],
        "resumed_from": None,
    }
    if parsed["delegation"] is not None:
        session["delegation"] = parsed["delegation"]
    return {
        "ok": True,
        "text": parsed["text"],
        "reason": None,
        "model": model_profile.get("model"),
        "reasoning_effort": model_profile.get("reasoning_effort"),
        "codex_profile": profile,
        "capability": capability,
        "orchestration": "codex_subagent" if require_subagent else "direct",
        "requested_intelligence": model_profile.get("requested_intelligence"),
        "resolved_intelligence": model_profile.get("resolved_intelligence"),
        "session": session,
        "usage": parsed["usage"],
    }
