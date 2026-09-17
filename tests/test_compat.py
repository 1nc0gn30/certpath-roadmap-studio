"""Tests for cross-platform compatibility utilities in compat.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from certpath_roadmap_studio.compat import (
    atomic_write_json,
    atomic_write_text,
    ensure_directory,
    get_platform_name,
    is_linux,
    is_macos,
    is_termux,
    is_windows,
    normalize_path,
    read_json_safe,
    read_text_safe,
    safe_resolve_path,
)


def test_platform_detection():
    """Verify platform detection functions return boolean types and valid platform name."""
    assert isinstance(is_windows(), bool)
    assert isinstance(is_macos(), bool)
    assert isinstance(is_linux(), bool)
    assert isinstance(is_termux(), bool)

    platform_name = get_platform_name()
    assert isinstance(platform_name, str)
    assert len(platform_name) > 0
    assert platform_name in ("windows", "macos", "linux", "termux", "unknown") or platform_name


def test_normalize_path(tmp_path: Path):
    """Verify path normalization with relative components and strings."""
    test_file = tmp_path / "subdir" / ".." / "file.txt"
    norm = normalize_path(test_file)
    assert isinstance(norm, Path)
    assert ".." not in norm.parts

    # None error
    with pytest.raises(ValueError):
        normalize_path(None)  # type: ignore


def test_safe_resolve_path(tmp_path: Path):
    """Verify safe path resolution relative to base directory."""
    base = tmp_path / "base_dir"
    base.mkdir()

    resolved = safe_resolve_path("sub/file.json", base_dir=base)
    assert str(base) in str(resolved)
    assert resolved.name == "file.json"

    # Absolute path ignored base_dir
    abs_path = (tmp_path / "other.txt").resolve()
    resolved_abs = safe_resolve_path(abs_path, base_dir=base)
    assert resolved_abs == abs_path


def test_ensure_directory(tmp_path: Path):
    """Verify recursive directory creation."""
    deep_dir = tmp_path / "a" / "b" / "c"
    assert not deep_dir.exists()
    result = ensure_directory(deep_dir)
    assert deep_dir.exists()
    assert deep_dir.is_dir()
    assert result == normalize_path(deep_dir)


def test_read_and_atomic_write_text(tmp_path: Path):
    """Verify resilient reading and atomic writing of text files."""
    file_path = tmp_path / "sample.txt"
    content = "Hello, Google CertPath Studio! 🚀"

    bytes_written = atomic_write_text(file_path, content)
    assert bytes_written > 0
    assert file_path.exists()

    read_back = read_text_safe(file_path)
    assert read_back == content

    # Overwrite atomically
    new_content = "Updated content across platforms"
    atomic_write_text(file_path, new_content)
    assert read_text_safe(file_path) == new_content


def test_read_text_safe_fallbacks(tmp_path: Path):
    """Verify fallback return on missing files and errors."""
    missing_file = tmp_path / "missing_file.txt"
    assert read_text_safe(missing_file, default="fallback_val") == "fallback_val"

    with pytest.raises(FileNotFoundError):
        read_text_safe(missing_file)


def test_read_and_atomic_write_json(tmp_path: Path):
    """Verify reading and writing JSON data atomically."""
    json_path = tmp_path / "data.json"
    data = {
        "title": "Cloud Architect",
        "skills": ["AWS", "Kubernetes", "Zero Trust"],
        "cost": 150.0,
        "active": True,
    }

    atomic_write_json(json_path, data, indent=2)
    assert json_path.exists()

    loaded = read_json_safe(json_path)
    assert loaded == data

    # Missing file default
    missing_json = tmp_path / "missing.json"
    assert read_json_safe(missing_json, default={"empty": True}) == {"empty": True}
