"""Tests for Command-Line Interface (CLI) in cli.py."""

from __future__ import annotations

import io
import json
import sys
from typing import List

import pytest

from certpath_roadmap_studio.cli import main


def run_cli_capture(args: List[str]) -> tuple[int, str, str]:
    """Execute CLI main with args and capture (exit_code, stdout, stderr)."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    out_buf, err_buf = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = out_buf, err_buf
    try:
        code = main(args)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return code or 0, out_buf.getvalue(), err_buf.getvalue()


def test_cli_version():
    """Verify -v and --version output."""
    code, out, _ = run_cli_capture(["--version"])
    assert code == 0
    assert "0.1.0" in out


def test_cli_stats_and_json():
    """Verify stats command output in text and JSON format."""
    code, out, _ = run_cli_capture(["stats", "--no-color"])
    assert code == 0
    assert "CertPath" in out or "Total Certifications" in out

    # JSON mode
    code_json, out_json, _ = run_cli_capture(["stats", "--json"])
    assert code_json == 0
    data = json.loads(out_json)
    total = data.get("total_certs") or data.get("catalog", {}).get("total_certs", 0)
    assert total >= 130


def test_cli_roles_and_json():
    """Verify roles command listing."""
    code, out, _ = run_cli_capture(["roles", "--no-color"])
    assert code == 0
    assert "cloud_security_architect" in out
    assert "ai_ml_engineer" in out

    # JSON mode
    code_json, out_json, _ = run_cli_capture(["roles", "--json"])
    assert code_json == 0
    roles = json.loads(out_json)
    if isinstance(roles, dict):
        roles = roles.get("roles", [])
    assert isinstance(roles, list)
    assert len(roles) >= 6


def test_cli_search():
    """Verify search subcommand with query, category, and level filters."""
    code, out, _ = run_cli_capture(["search", "AWS", "--no-color"])
    assert code == 0
    assert "AWS" in out

    # Search with filters and JSON output
    code_json, out_json, _ = run_cli_capture(["search", "--category", "Cyber Security", "--level", "Entry", "--json"])
    assert code_json == 0
    data = json.loads(out_json)
    results = data.get("results", data) if isinstance(data, dict) else data
    assert isinstance(results, list)
    assert len(results) > 0
    assert all(r["category"] == "Cyber Security" for r in results)


def test_cli_prereqs_and_unlocked():
    """Verify prereqs and unlocked subcommands."""
    # Prereqs for cissp
    code, out, _ = run_cli_capture(["prereqs", "cyber-cissp", "--no-color"])
    assert code == 0
    assert "Prerequisite Chain" in out or "cyber-cissp" in out

    # Prereqs JSON
    code_json, out_json, _ = run_cli_capture(["prereqs", "cyber-cissp", "--json"])
    assert code_json == 0
    data = json.loads(out_json)
    prereqs = data.get("chain", data) if isinstance(data, dict) else data
    assert isinstance(prereqs, list)

    # Unlocked for Network+
    code_u, out_u, _ = run_cli_capture(["unlocked", "soft-comptia-network-plus", "--no-color"])
    assert code_u == 0
    assert "Credentials Unlocked" in out_u or "soft-comptia-network-plus" in out_u or "Unlocked" in out_u


def test_cli_plan():
    """Verify plan subcommand with role and various output formats."""
    # Text format
    code, out, _ = run_cli_capture(["plan", "--role", "cloud_security_architect", "--hours", "15", "--no-color"])
    assert code == 0
    assert "Cloud Security Architect" in out
    assert "Phase" in out

    # JSON format
    code_j, out_j, _ = run_cli_capture(["plan", "--role", "ai_ml_engineer", "--format", "json"])
    assert code_j == 0
    plan_data = json.loads(out_j)
    assert plan_data["target_name"] == "AI & Machine Learning Engineer"
    assert "phases" in plan_data

    # Markdown format
    code_m, out_m, _ = run_cli_capture(["plan", "--role", "fullstack_devops_lead", "--format", "md"])
    assert code_m == 0
    assert "# 🗺️" in out_m


def test_cli_compare():
    """Verify compare subcommand with side-by-side output."""
    code, out, _ = run_cli_capture(["compare", "cyber-sec-plus", "cyber-cysa-plus", "--no-color"])
    assert code == 0
    assert "CompTIA Security+" in out
    assert "CompTIA CySA+" in out

    # JSON format
    code_j, out_j, _ = run_cli_capture(["compare", "cyber-sec-plus", "cyber-cysa-plus", "--json"])
    assert code_j == 0
    compared = json.loads(out_j)
    if isinstance(compared, dict):
        compared = compared.get("comparisons", compared.get("results", []))
    assert len(compared) == 2


def test_cli_mermaid_and_tree():
    """Verify mermaid and tree export subcommands."""
    code_m, out_m, _ = run_cli_capture(["mermaid", "cloud_security_architect"])
    assert code_m == 0
    assert "flowchart" in out_m or "graph" in out_m

    code_t, out_t, _ = run_cli_capture(["tree", "cyber-cissp", "--no-color"])
    assert code_t == 0
    assert "Target:" in out_t


def test_cli_doctor_and_diagnostics():
    """Verify doctor / diagnostics command."""
    code, out, _ = run_cli_capture(["doctor", "--no-color"])
    assert code == 0
    assert "CertPath" in out and "Diagnostics" in out
    assert "Status" in out or "healthy" in out
