"""Cross-platform compatibility utilities for CertPath Roadmap Studio.

Provides safe path normalization, atomic file operations, and resilient
text/JSON reading and writing across Linux, macOS, Windows, and Termux (Android).
Zero third-party dependencies (100% Python Standard Library).
"""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Optional, Union

# List of text encodings to attempt when reading files safely
FALLBACK_ENCODINGS: List[str] = [
    "utf-8",
    "utf-8-sig",
    "latin-1",
    "cp1252",
    "iso-8859-1",
]


def is_windows() -> bool:
    """Return True if running on a Microsoft Windows operating system."""
    return sys.platform.startswith("win") or platform.system() == "Windows"


def is_macos() -> bool:
    """Return True if running on Apple macOS / Darwin."""
    return sys.platform == "darwin" or platform.system() == "Darwin"


def is_linux() -> bool:
    """Return True if running on Linux (including WSL and Termux)."""
    return sys.platform.startswith("linux") or platform.system() == "Linux"


def is_termux() -> bool:
    """Return True if running inside an Android Termux environment."""
    return (
        "com.termux" in os.environ.get("PREFIX", "")
        or "com.termux" in os.environ.get("PATH", "")
        or "ANDROID_ROOT" in os.environ
        or "/data/data/com.termux" in os.environ.get("HOME", "")
    )


def get_platform_name() -> str:
    """Return normalized human-readable platform name."""
    if is_termux():
        return "termux"
    if is_windows():
        return "windows"
    if is_macos():
        return "macos"
    if is_linux():
        return "linux"
    return sys.platform or "unknown"


def normalize_path(path: Union[str, Path, os.PathLike]) -> Path:
    """Normalize a path safely across POSIX and Windows environments.

    Expands user home directory `~`, resolves relative components (`.` and `..`),
    and normalizes path separators.
    """
    if path is None:
        raise ValueError("Path cannot be None")
    path_str = os.fspath(path)
    # Expand user directory
    expanded = os.path.expanduser(os.path.expandvars(path_str))
    # Create Path object and resolve
    p = Path(expanded)
    try:
        return p.resolve()
    except (RuntimeError, OSError):
        # Fallback if resolve fails due to permissions or broken symlinks
        return p.absolute()


def safe_resolve_path(
    path: Union[str, Path, os.PathLike],
    base_dir: Optional[Union[str, Path, os.PathLike]] = None,
) -> Path:
    """Resolve path relative to base_dir if relative, else resolve directly."""
    p = Path(os.fspath(path))
    if not p.is_absolute() and base_dir is not None:
        base = normalize_path(base_dir)
        return normalize_path(base / p)
    return normalize_path(p)


def ensure_directory(path: Union[str, Path, os.PathLike]) -> Path:
    """Ensure directory exists, creating parents if necessary.

    Returns the normalized Path of the directory.
    """
    p = normalize_path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_text_safe(
    path: Union[str, Path, os.PathLike],
    encodings: Optional[List[str]] = None,
    default: Optional[str] = None,
) -> str:
    """Read file content with multi-encoding fallback.

    If file is not found and `default` is provided, returns `default`.
    Otherwise raises `FileNotFoundError`.
    """
    p = normalize_path(path)
    if not p.exists() or not p.is_file():
        if default is not None:
            return default
        raise FileNotFoundError(f"File not found: {p}")

    encoding_list = encodings or FALLBACK_ENCODINGS
    last_error: Optional[Exception] = None

    for enc in encoding_list:
        try:
            with open(p, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError) as err:
            last_error = err
            continue

    # Final attempt with replace error handler
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as err:
        raise OSError(f"Failed to read file {p} with available encodings: {last_error or err}") from last_error


def atomic_write_text(
    path: Union[str, Path, os.PathLike],
    content: str,
    encoding: str = "utf-8",
) -> int:
    """Atomically write text content to a file.

    Writes to a temporary file in the target directory first, then replaces
    the destination file via `os.replace` to prevent corrupted partial writes.
    Returns the number of characters written.
    """
    target = normalize_path(path)
    parent_dir = target.parent
    ensure_directory(parent_dir)

    # Use NamedTemporaryFile in the same directory to guarantee same filesystem (for atomic rename)
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            dir=parent_dir,
            delete=False,
            prefix=f".tmp_{target.name}_",
            suffix=".tmp",
        ) as tmp:
            temp_file = Path(tmp.name)
            bytes_written = tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())

        # Atomically replace target with temp file
        os.replace(temp_file, target)
        temp_file = None
        return bytes_written
    except Exception as err:
        # Fallback to direct write if tempfile atomic rename fails (e.g. permission or special FS)
        try:
            with open(target, "w", encoding=encoding) as f:
                return f.write(content)
        except Exception as direct_err:
            raise OSError(f"Failed atomic and direct write to {target}: {direct_err}") from err
    finally:
        if temp_file is not None and temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass


def read_json_safe(
    path: Union[str, Path, os.PathLike],
    default: Any = None,
) -> Any:
    """Safely read and parse a JSON file with multi-encoding fallback.

    Returns `default` if file does not exist or JSON parsing fails with default provided.
    """
    try:
        content = read_text_safe(path)
        return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        if default is not None:
            return default
        raise


def atomic_write_json(
    path: Union[str, Path, os.PathLike],
    data: Any,
    indent: int = 2,
    encoding: str = "utf-8",
    ensure_ascii: bool = False,
) -> int:
    """Atomically write Python data structure as formatted JSON."""
    serialized = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
    return atomic_write_text(path, serialized, encoding=encoding)
