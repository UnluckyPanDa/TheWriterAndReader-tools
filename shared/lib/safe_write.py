"""Safe file writing helpers constrained to an allowed root."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


def assert_inside_root(path: str | Path, root: str | Path) -> None:
    """Raise ValueError when path is outside root."""
    candidate = Path(path).expanduser().resolve(strict=False)
    allowed_root = Path(root).expanduser().resolve(strict=False)
    if candidate != allowed_root and allowed_root not in candidate.parents:
        raise ValueError(f"Refusing to access path outside allowed root: {candidate} not under {allowed_root}")


def safe_mkdir(path: str | Path, allowed_root: str | Path) -> Path:
    """Create a directory after checking it is inside the allowed root."""
    directory = Path(path).expanduser().resolve(strict=False)
    assert_inside_root(directory, allowed_root)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def create_backup_before_write(path: str | Path) -> Path | None:
    """Create a timestamp-light backup for an existing file and return its path."""
    target = Path(path).expanduser().resolve(strict=False)
    if not target.exists():
        return None
    backup = target.with_suffix(target.suffix + ".bak")
    counter = 1
    while backup.exists():
        backup = target.with_suffix(target.suffix + f".bak{counter}")
        counter += 1
    shutil.copy2(target, backup)
    return backup


def atomic_write(path: str | Path, content: str) -> None:
    """Atomically write text content to path using a temporary file in the same directory."""
    target = Path(path).expanduser().resolve(strict=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(target)


def safe_write_file(path: str | Path, content: str, allowed_root: str | Path) -> Path:
    """Write a text file only when the destination is inside allowed_root."""
    target = Path(path).expanduser().resolve(strict=False)
    assert_inside_root(target, allowed_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(target, content)
    return target


def safe_copy_file(src: str | Path, dst: str | Path, allowed_root: str | Path) -> Path:
    """Copy a file to a destination inside allowed_root."""
    source = Path(src).expanduser().resolve(strict=True)
    target = Path(dst).expanduser().resolve(strict=False)
    assert_inside_root(target, allowed_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target
