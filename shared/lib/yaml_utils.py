"""Small YAML helpers with a PyYAML fallback for MVP fixtures and config."""

from __future__ import annotations

from typing import Any

try:
    import yaml as _pyyaml
except ImportError:  # pragma: no cover - exercised when PyYAML is unavailable
    _pyyaml = None


def load_yaml_text(text: str) -> Any:
    """Load YAML text using PyYAML when available, otherwise a small subset parser."""
    if _pyyaml is not None:
        return _pyyaml.safe_load(text)
    return _parse_block(_clean_lines(text), 0, 0)[0]


def dump_yaml(data: Any, sort_keys: bool = False) -> str:
    """Dump YAML using PyYAML when available, otherwise a small deterministic subset."""
    if _pyyaml is not None:
        return _pyyaml.safe_dump(data, sort_keys=sort_keys)
    lines = _dump_value(data, 0, sort_keys)
    return "\n".join(lines) + "\n"


def _clean_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append((indent, raw_line.strip()))
    return lines


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines) or lines[index][0] < indent:
        return {}, index
    if lines[index][1].startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_list(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    values: list[Any] = []
    while index < len(lines):
        line_indent, line = lines[index]
        if line_indent != indent or not line.startswith("- "):
            break
        item = line[2:].strip()
        index += 1
        if not item:
            child, index = _parse_block(lines, index, indent + 2)
            values.append(child)
        elif ":" in item and not item.startswith(("'", '"')):
            key, value = item.split(":", 1)
            mapped: dict[str, Any] = {key.strip(): _parse_scalar(value.strip())}
            if index < len(lines) and lines[index][0] > indent:
                child, index = _parse_block(lines, index, indent + 2)
                if isinstance(child, dict):
                    mapped.update(child)
            values.append(mapped)
        else:
            values.append(_parse_scalar(item))
    return values, index


def _parse_mapping(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    values: dict[str, Any] = {}
    while index < len(lines):
        line_indent, line = lines[index]
        if line_indent != indent or line.startswith("- "):
            break
        if ":" not in line:
            raise ValueError(f"Unsupported YAML line: {line}")
        key, value = line.split(":", 1)
        index += 1
        if value.strip():
            values[key.strip()] = _parse_scalar(value.strip())
        else:
            child, index = _parse_block(lines, index, indent + 2)
            values[key.strip()] = child
    return values, index


def _parse_scalar(value: str) -> Any:
    if value in {"", "null", "Null", "NULL", "~"}:
        return None
    if value in {"true", "True", "TRUE"}:
        return True
    if value in {"false", "False", "FALSE"}:
        return False
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _dump_value(value: Any, indent: int, sort_keys: bool) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        items = sorted(value.items()) if sort_keys else value.items()
        lines: list[str] = []
        for key, item in items:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(_dump_value(item, indent + 2, sort_keys))
            else:
                lines.append(f"{prefix}{key}: {_format_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.extend(_dump_value(item, indent + 2, sort_keys))
            else:
                lines.append(f"{prefix}- {_format_scalar(item)}")
        return lines
    return [f"{prefix}{_format_scalar(value)}"]


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
