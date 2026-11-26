"""Comprehensive security hardening and regression test suite for v2.6.0.

Covers:
- Strict loopback Host header allowlist (DNS rebinding guard)
- Strict CORS Origin parsing & port-suffix spoof rejection (GET, OPTIONS, POST)
- Mandatory security headers & Vary: Origin
- MAX_BODY_BYTES (413), malformed/negative/missing Content-Length (400)
- Malformed and non-dict JSON bodies ([], null, 123, "str") -> 400 JSON
- Numeric validation (abc, NaN, negative limit) -> 400 JSON, zero NaN serialization
- HEAD /health, /api/health, / (200 OK, 0 B body)
- Symlink static escape containment (403)
- Legal & support routes (/terms, /privacy, /support -> 200 OK)
- Free-certification ROI math (web-html-css -> five_year_roi_pct is None)
- MCP stdio fuzz resilience (-32600 / -32602, zero crashes, zero RuntimeWarning)
"""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Tuple

import pytest

from certpath_roadmap_studio.catalog import CertificationCatalog
from certpath_roadmap_studio.roi_calculator import calculate_cert_roi
from certpath_roadmap_studio.ui_server import MAX_BODY_BYTES, _is_local_origin, _is_valid_host


def _raw_http(
    port: int,
    method: str,
    path: str,
    headers: dict | None = None,
    body: bytes | None = None,
) -> Tuple[int, dict, bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        hdrs = dict(headers or {})
        conn.putrequest(method, path, skip_host=("Host" in hdrs))
        for k, v in hdrs.items():
            conn.putheader(k, v)
        if body is not None and "Content-Length" not in hdrs:
            conn.putheader("Content-Length", str(len(body)))
        conn.endheaders()
        if body is not None:
            conn.send(body)
        resp = conn.getresponse()
        data = resp.read()
        resp_headers = {k.lower(): v for k, v in resp.getheaders()}
        return resp.status, resp_headers, data
    finally:
        conn.close()


def test_host_and_origin_validators():
    assert _is_valid_host("127.0.0.1")
    assert _is_valid_host("127.0.0.1:8093")
    assert _is_valid_host("localhost:3000")
    assert _is_valid_host("[::1]:8093")
    assert not _is_valid_host("evil.example.invalid")
    assert not _is_valid_host("127.0.0.1:8093.example.invalid")
    assert not _is_valid_host("127.0.0.1:99999")
    assert not _is_valid_host("127.0.0.1:abc")
    assert not _is_valid_host("")
    assert not _is_valid_host(None)

    assert _is_local_origin(None)
    assert _is_local_origin("")
    assert _is_local_origin("http://127.0.0.1:8093")
    assert _is_local_origin("http://localhost:3000")
    assert _is_local_origin("http://[::1]:8093")
    assert _is_local_origin("https://certpath-roadmap-studio.netlify.app")
    assert not _is_local_origin("http://127.0.0.1:8093.example.invalid")
    assert not _is_local_origin("http://localhost:3000.evil.example")
    assert not _is_local_origin("https://example.invalid")
    assert not _is_local_origin("http://user@127.0.0.1:8093")
    assert not _is_local_origin("http://127.0.0.1:8093/path")


def test_host_header_rebinding_blocked(test_server: Tuple[str, int]):
    _, port = test_server
    for method, path in (("GET", "/api/stats"), ("HEAD", "/health"), ("OPTIONS", "/api/plan"), ("POST", "/api/search")):
        status, hdrs, body = _raw_http(
            port,
            method,
            path,
            headers={"Host": "evil.example.invalid", "Content-Length": "2"} if method == "POST" else {"Host": "evil.example.invalid"},
            body=b"{}" if method == "POST" else None,
        )
        assert status == 403
        assert "access-control-allow-origin" not in hdrs
        assert hdrs.get("vary") == "Origin"
        assert hdrs.get("x-content-type-options") == "nosniff"
        if method != "HEAD":
            payload = json.loads(body.decode("utf-8"))
            assert payload["status"] == 403


def test_cors_port_suffix_spoof_rejected_all_methods(test_server: Tuple[str, int]):
    _, port = test_server
    spoof_origins = (
        "http://127.0.0.1:8093.example.invalid",
        "https://example.invalid",
    )
    for origin in spoof_origins:
        for method, path in (("GET", "/api/stats"), ("OPTIONS", "/api/plan"), ("POST", "/api/search")):
            hdrs_in = {"Origin": origin}
            body_in = None
            if method == "POST":
                body_in = b'{"query": "aws"}'
                hdrs_in["Content-Type"] = "application/json"
            status, hdrs, body = _raw_http(port, method, path, headers=hdrs_in, body=body_in)
            assert status == 403, f"Expected 403 for {method} {origin}, got {status}"
            assert "access-control-allow-origin" not in hdrs
            assert hdrs.get("vary") == "Origin"
            payload = json.loads(body.decode("utf-8"))
            assert payload["status"] == 403


def test_security_headers_and_head_requests(test_server: Tuple[str, int]):
    _, port = test_server
    for path in ("/", "/health", "/api/health", "/terms", "/privacy", "/support"):
        status, hdrs, body = _raw_http(port, "HEAD", path)
        assert status == 200
        assert body == b""
        assert hdrs.get("x-content-type-options") == "nosniff"
        assert hdrs.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert "frame-ancestors" in hdrs.get("content-security-policy", "")
        assert "http://127.0.0.1:*" in hdrs.get("content-security-policy", "")
        assert hdrs.get("vary") == "Origin"

        g_status, g_hdrs, g_body = _raw_http(port, "GET", path)
        assert g_status == 200
        assert len(g_body) > 0
        assert g_hdrs.get("x-content-type-options") == "nosniff"


def test_body_size_limit_and_malformed_content_length(test_server: Tuple[str, int]):
    _, port = test_server

    # > 1 MiB rejected with 413 before reading
    status, hdrs, body = _raw_http(
        port,
        "POST",
        "/api/search",
        headers={"Content-Type": "application/json", "Content-Length": str(MAX_BODY_BYTES + 1024)},
    )
    assert status == 413
    assert json.loads(body.decode("utf-8"))["status"] == 413

    # Non-integer Content-Length -> 400 JSON without dropping connection
    status, _, body = _raw_http(
        port,
        "POST",
        "/api/search",
        headers={"Content-Type": "application/json", "Content-Length": "abc"},
    )
    assert status == 400
    assert json.loads(body.decode("utf-8"))["status"] == 400

    # Negative Content-Length -> 400 JSON
    status, _, body = _raw_http(
        port,
        "POST",
        "/api/search",
        headers={"Content-Type": "application/json", "Content-Length": "-5"},
    )
    assert status == 400
    assert json.loads(body.decode("utf-8"))["status"] == 400

    # Missing Content-Length -> 400 JSON
    status, _, body = _raw_http(
        port,
        "POST",
        "/api/search",
        headers={"Content-Type": "application/json"},
    )
    assert status == 400
    assert json.loads(body.decode("utf-8"))["status"] == 400


def test_malformed_and_non_dict_json_bodies(test_server: Tuple[str, int]):
    _, port = test_server
    for raw_payload in (b"{broken", b"[]", b"null", b"123", b'"str"'):
        status, _, body = _raw_http(
            port,
            "POST",
            "/api/plan",
            headers={"Content-Type": "application/json"},
            body=raw_payload,
        )
        assert status == 400, f"Expected 400 for payload {raw_payload!r}, got {status}"
        assert json.loads(body.decode("utf-8"))["status"] == 400


def test_numeric_validation_and_nan_rejection(test_server: Tuple[str, int]):
    _, port = test_server

    def _reject_constant(val: str):
        raise AssertionError(f"Non-standard JSON constant encountered: {val}")

    # GET bad query numbers
    for bad_path in (
        "/api/simulate-velocity?hours=abc",
        "/api/simulate-velocity?trials=abc",
        "/api/simulate-velocity?hours=0",
        "/api/simulate-velocity?hours=NaN",
        "/api/catalog?limit=-1",
        "/api/catalog?limit=abc",
        "/api/plan?hours=abc",
        "/api/plan?budget=NaN",
    ):
        status, _, body = _raw_http(port, "GET", bad_path)
        assert status == 400, f"Expected 400 for {bad_path}, got {status}"
        parsed = json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
        assert parsed["status"] == 400

    # POST bad body numbers
    for path, payload in (
        ("/api/plan", {"weekly_hours": "abc"}),
        ("/api/plan", {"max_budget": "NaN"}),
        ("/api/plan", {"max_budget": -50}),
        ("/api/search", {"limit": -1}),
        ("/api/simulate-velocity", {"weekly_hours": "abc"}),
        ("/api/simulate-velocity", {"trials": 99999}),
    ):
        status, _, body = _raw_http(
            port,
            "POST",
            path,
            headers={"Content-Type": "application/json"},
            body=json.dumps(payload).encode("utf-8"),
        )
        assert status == 400, f"Expected 400 for POST {path} {payload}, got {status}"
        parsed = json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
        assert parsed["status"] == 400


def test_symlink_static_escape_blocked(test_server: Tuple[str, int], tmp_path: Path):
    _, port = test_server
    from certpath_roadmap_studio.ui_server import StudioHTTPRequestHandler

    pub_dir = StudioHTTPRequestHandler.public_dir
    assert pub_dir is not None
    outside_secret = tmp_path / "outside_secret.txt"
    outside_secret.write_text("TOP_SECRET_DATA", encoding="utf-8")
    link_path = pub_dir / "escape_link.txt"
    if link_path.exists() or link_path.is_symlink():
        link_path.unlink()
    os.symlink(outside_secret, link_path)
    try:
        status, _, body = _raw_http(port, "GET", "/escape_link.txt")
        assert status in (403, 404)
        assert b"TOP_SECRET_DATA" not in body
    finally:
        link_path.unlink(missing_ok=True)


def test_free_cert_roi_no_absurd_percentage():
    cat = CertificationCatalog()
    free_cert = cat.get("web-html-css")
    assert free_cert is not None
    roi = calculate_cert_roi(free_cert)
    assert roi.exam_cost_usd == 0.0
    assert roi.payback_period_months == 0.0
    assert roi.five_year_roi_pct is None
    assert "Free" in roi.roi_label
    assert roi.annual_salary_premium_usd > 0


def test_mcp_stdio_fuzz_and_zero_runtime_warning():
    repo_src = str(Path(__file__).resolve().parent.parent / "src")
    env = os.environ.copy()
    env["PYTHONPATH"] = repo_src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    lines = [
        "{broken",
        "[]",
        "null",
        "123",
        '"str"',
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": None}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": "str"}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "certpath_calculate_roi", "arguments": "str"}}),
        json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "certpath_calculate_roi", "arguments": {"cert_id": 123}}}),
        json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "certpath_simulate_velocity", "arguments": {"target": "soc_analyst", "weekly_hours": "bad"}}}),
        json.dumps({"jsonrpc": "2.0", "id": 6, "method": "initialize", "params": {}}),
    ]
    proc = subprocess.run(
        [sys.executable, "-m", "certpath_roadmap_studio.mcp_server"],
        input="\n".join(lines) + "\n",
        text=True,
        capture_output=True,
        env=env,
        timeout=15,
    )
    assert proc.returncode == 0
    assert "RuntimeWarning" not in proc.stderr
    assert "Traceback" not in proc.stderr

    out_lines = [json.loads(line) for line in proc.stdout.strip().splitlines() if line.strip()]
    assert len(out_lines) == len(lines)
    assert out_lines[0]["error"]["code"] == -32700  # {broken
    assert out_lines[1]["error"]["code"] == -32600  # []
    assert out_lines[2]["error"]["code"] == -32600  # null
    assert out_lines[3]["error"]["code"] == -32600  # 123
    assert out_lines[4]["error"]["code"] == -32600  # "str"
    assert out_lines[5]["error"]["code"] == -32602  # params: null
    assert out_lines[6]["error"]["code"] == -32602  # params: "str"
    assert out_lines[7]["error"]["code"] == -32602  # arguments: "str"
    assert out_lines[8]["error"]["code"] == -32602  # cert_id: 123
    assert out_lines[9]["error"]["code"] == -32602  # weekly_hours: "bad"
    assert out_lines[10]["result"]["serverInfo"]["version"] == "2.6.0"
