"""Tests for UI Web Server and REST API endpoints in ui_server.py."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Tuple

import pytest


def make_request(
    url: str,
    method: str = "GET",
    data: dict = None,
    headers: dict = None,
) -> Tuple[int, dict, bytes]:
    """Helper to perform HTTP requests against test server."""
    req_headers = headers or {}
    body_bytes = None
    if data is not None:
        body_bytes = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            resp_headers = dict(resp.headers)
            content = resp.read()
            return status, resp_headers, content
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_ui_index_and_static_files(test_server: Tuple[str, int]):
    """Verify serving HTML index and JSON datasets."""
    base_url, _ = test_server

    # GET /
    status, headers, content = make_request(f"{base_url}/")
    assert status == 200
    assert "text/html" in headers.get("Content-Type", "")

    # GET /certs.json
    status, headers, content = make_request(f"{base_url}/certs.json")
    assert status == 200
    certs_data = json.loads(content.decode("utf-8"))
    assert isinstance(certs_data, list)
    assert len(certs_data) == 5


def test_api_catalog_endpoint(test_server: Tuple[str, int]):
    """Verify /api/catalog search and query parameter filtering."""
    base_url, _ = test_server

    # All certs
    status, _, content = make_request(f"{base_url}/api/catalog")
    assert status == 200
    all_certs = json.loads(content.decode("utf-8"))
    assert len(all_certs) == 5

    # Filter by query
    status, _, content = make_request(f"{base_url}/api/catalog?q=Subnetting")
    assert status == 200
    filtered = json.loads(content.decode("utf-8"))
    assert len(filtered) == 1
    assert filtered[0]["id"] == "cert-entry-2"

    # Filter with limit
    status, _, content = make_request(f"{base_url}/api/catalog?limit=2")
    assert status == 200
    limited = json.loads(content.decode("utf-8"))
    assert len(limited) == 2


def test_api_cert_and_prereqs_endpoints(test_server: Tuple[str, int]):
    """Verify /api/cert/<id>, /api/prereqs/<id>, and /api/unlocked/<id>."""
    base_url, _ = test_server

    # Single cert details
    status, _, content = make_request(f"{base_url}/api/cert/cert-adv-1")
    assert status == 200
    cert_data = json.loads(content.decode("utf-8"))
    assert cert_data["id"] == "cert-adv-1"
    assert "resolvedPrerequisites" in cert_data
    assert len(cert_data["resolvedPrerequisites"]) == 4
    assert "difficultyScore" in cert_data

    # 404 for missing cert
    status, _, content = make_request(f"{base_url}/api/cert/non-existent-id")
    assert status == 404

    # Prereqs endpoint
    status, _, content = make_request(f"{base_url}/api/prereqs/cert-adv-1")
    assert status == 200
    prereqs_data = json.loads(content.decode("utf-8"))
    assert prereqs_data["count"] == 4
    assert len(prereqs_data["prerequisites"]) == 4

    # Unlocked endpoint
    status, _, content = make_request(f"{base_url}/api/unlocked/cert-entry-1")
    assert status == 200
    unlocked_data = json.loads(content.decode("utf-8"))
    assert unlocked_data["count"] >= 2


def test_api_plan_get_and_post(test_server: Tuple[str, int]):
    """Verify /api/plan roadmap generation via GET and POST."""
    base_url, _ = test_server

    # GET /api/plan
    status, _, content = make_request(f"{base_url}/api/plan?role=cloud_sec_lead&hours=15")
    assert status == 200
    plan_get = json.loads(content.decode("utf-8"))
    assert plan_get["target_name"] == "Cloud Security Lead"
    assert plan_get["weekly_hours"] == 15
    assert len(plan_get["phases"]) > 0

    # POST /api/plan
    post_payload = {
        "role": "cloud_sec_lead",
        "current_certs": ["cert-entry-1"],
        "weekly_hours": 20,
    }
    status, _, content = make_request(f"{base_url}/api/plan", method="POST", data=post_payload)
    assert status == 200
    plan_post = json.loads(content.decode("utf-8"))
    assert plan_post["target_name"] == "Cloud Security Lead"
    assert plan_post["weekly_hours"] == 20


def test_api_compare_and_roles(test_server: Tuple[str, int]):
    """Verify /api/compare and /api/roles endpoints."""
    base_url, _ = test_server

    # GET /api/compare
    status, _, content = make_request(f"{base_url}/api/compare?ids=cert-entry-1,cert-inter-1")
    assert status == 200
    compare_data = json.loads(content.decode("utf-8"))
    assert compare_data["count"] == 2
    assert len(compare_data["certifications"]) == 2

    # GET /api/roles
    status, _, content = make_request(f"{base_url}/api/roles")
    assert status == 200
    roles_data = json.loads(content.decode("utf-8"))
    assert isinstance(roles_data, list)
    assert any(r["role_id"] == "cloud_sec_lead" for r in roles_data)


def test_api_stats_and_diagnostics(test_server: Tuple[str, int]):
    """Verify /api/stats, /api/mermaid, and /api/diagnostics."""
    base_url, _ = test_server

    # Stats
    status, _, content = make_request(f"{base_url}/api/stats")
    assert status == 200
    stats = json.loads(content.decode("utf-8"))
    assert stats["total_certs"] == 5
    assert stats["is_dag"] is True

    # Mermaid
    status, _, content = make_request(f"{base_url}/api/mermaid?direction=TD")
    assert status == 200
    mermaid_data = json.loads(content.decode("utf-8"))
    assert "mermaid" in mermaid_data
    assert mermaid_data["direction"] == "TD"

    # Diagnostics
    status, _, content = make_request(f"{base_url}/api/diagnostics")
    assert status == 200
    diag = json.loads(content.decode("utf-8"))
    assert diag["status"] == "healthy"
    assert "platform" in diag
    assert "python_version" in diag


def test_cors_options_preflight(test_server: Tuple[str, int]):
    """Verify CORS preflight OPTIONS request returns permissive headers."""
    base_url, _ = test_server
    status, headers, _ = make_request(f"{base_url}/api/catalog", method="OPTIONS")
    assert status in (200, 204)
    assert headers.get("Access-Control-Allow-Origin") == "*"
    assert "GET" in headers.get("Access-Control-Allow-Methods", "")


def test_api_roi_overlap_valuation(test_server: Tuple[str, int]):
    """Verify /api/roi, /api/overlap, and /api/valuation GET and POST endpoints."""
    base_url, _ = test_server

    # GET /api/roi
    status, _, content = make_request(f"{base_url}/api/roi?cert_id=cert-entry-1")
    assert status == 200
    roi_data = json.loads(content.decode("utf-8"))
    assert roi_data["cert_id"] == "cert-entry-1"
    assert "annual_salary_premium_usd" in roi_data

    # POST /api/roi
    status, _, content = make_request(f"{base_url}/api/roi", method="POST", data={"cert_id": "cert-entry-1"})
    assert status == 200
    roi_post = json.loads(content.decode("utf-8"))
    assert roi_post["cert_id"] == "cert-entry-1"

    # GET /api/overlap
    status, _, content = make_request(f"{base_url}/api/overlap?cert_a=cert-entry-1&cert_b=cert-inter-1")
    assert status == 200
    ov_data = json.loads(content.decode("utf-8"))
    assert "overlap_ratio" in ov_data

    # POST /api/overlap
    status, _, content = make_request(f"{base_url}/api/overlap", method="POST", data={"cert_a": "cert-entry-1", "cert_b": "cert-inter-1"})
    assert status == 200
    ov_post = json.loads(content.decode("utf-8"))
    assert "overlap_ratio" in ov_post

    # GET /api/valuation
    status, _, content = make_request(f"{base_url}/api/valuation?certs=cert-entry-1,cert-inter-1")
    assert status == 200
    val_data = json.loads(content.decode("utf-8"))
    assert val_data["total_credentials"] == 2

    # POST /api/valuation
    status, _, content = make_request(f"{base_url}/api/valuation", method="POST", data={"cert_ids": ["cert-entry-1", "cert-inter-1"]})
    assert status == 200
    val_post = json.loads(content.decode("utf-8"))
    assert val_post["total_credentials"] == 2

