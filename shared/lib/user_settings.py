"""Persist non-secret settings for the local TWR web interface."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from shared.lib.yaml_utils import dump_yaml, load_yaml_text


DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "dark",
    "language": "en",
    "workspace_history": [],
}
MAX_WORKSPACE_HISTORY = 12


def get_user_settings_path() -> Path:
    """Return the local UI settings path, honoring TWR_UI_SETTINGS for tests."""
    configured = os.environ.get("TWR_UI_SETTINGS")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".config" / "the-writer-and-reader" / "ui-settings.yaml"


def _normalise(data: Any) -> dict[str, Any]:
    settings = dict(data) if isinstance(data, dict) else {}
    theme = settings.get("theme")
    settings["theme"] = theme if theme in {"dark", "light"} else DEFAULT_SETTINGS["theme"]
    language = settings.get("language")
    settings["language"] = language if language in {"en", "zh-Hant"} else DEFAULT_SETTINGS["language"]

    history: list[str] = []
    for path in settings.get("workspace_history", []):
        if isinstance(path, str) and path.strip() and path not in history:
            history.append(path)
    settings["workspace_history"] = history[:MAX_WORKSPACE_HISTORY]
    return settings


def load_user_settings() -> dict[str, Any]:
    """Load local UI settings, returning safe defaults when absent or invalid."""
    path = get_user_settings_path()
    if not path.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        data = load_yaml_text(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return _normalise(data)


def save_user_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Persist local UI settings and return the normalised values."""
    path = get_user_settings_path()
    normalised = _normalise({**load_user_settings(), **settings})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml(normalised, sort_keys=False), encoding="utf-8")
    return normalised
