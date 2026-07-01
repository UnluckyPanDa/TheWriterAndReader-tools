"""Load series metadata and series-level context files."""
from __future__ import annotations

from pathlib import Path

from shared.lib.yaml_utils import load_yaml_text


def load_series_yaml(series_path: str | Path) -> dict:
    """Load series.yaml from a series directory."""
    path = Path(series_path).expanduser().resolve(strict=False) / "series.yaml"
    if not path.exists():
        raise FileNotFoundError(f"series.yaml not found: {path}")
    data = load_yaml_text(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"series.yaml must contain a mapping: {path}")
    return data


def _load_text(series_path: str | Path, relative: str) -> str:
    path = Path(series_path).expanduser().resolve(strict=False) / relative
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_series_canon(series_path: str | Path) -> str:
    """Load series_canon.md."""
    return _load_text(series_path, "series_canon.md")


def load_series_timeline(series_path: str | Path) -> str:
    """Load timeline.md."""
    return _load_text(series_path, "timeline.md")


def load_series_timeline_states(series_path: str | Path) -> str:
    """Load timeline_states.md."""
    return _load_text(series_path, "timeline_states.md")


def load_series_pack(series_path: str | Path) -> str:
    """Load context/series_pack.md."""
    return _load_text(series_path, "context/series_pack.md")


def load_series(series_path: str | Path) -> dict:
    """Load series metadata and compact context files."""
    return {
        "path": str(Path(series_path).expanduser().resolve(strict=False)),
        "series": load_series_yaml(series_path),
        "canon": load_series_canon(series_path),
        "timeline": load_series_timeline(series_path),
        "timeline_states": load_series_timeline_states(series_path),
        "series_pack": load_series_pack(series_path),
    }
