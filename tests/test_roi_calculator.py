"""Unit and integration tests for Certification ROI, Compensation & Skill Overlap Matrix Engine.

Tests ROI financial calculations, payback horizons, Jaccard skill overlap,
portfolio diversification (HHI), MCP tools, CLI commands, and REST endpoints.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from certpath_roadmap_studio.catalog import CertificationCatalog
from certpath_roadmap_studio.cli import main
from certpath_roadmap_studio.dag_engine import DAGEngine
from certpath_roadmap_studio.mcp_server import MCPServer
from certpath_roadmap_studio.roadmap_planner import RoadmapPlanner
from certpath_roadmap_studio.roi_calculator import (
    CertROIAnalysis,
    PortfolioValuation,
    SkillOverlapResult,
    calculate_cert_roi,
    calculate_skill_overlap,
    evaluate_portfolio,
    format_portfolio_scorecard,
    format_roi_scorecard,
)


@pytest.fixture
def catalog() -> CertificationCatalog:
    return CertificationCatalog()


@pytest.fixture
def mcp_server(catalog) -> MCPServer:
    dag = DAGEngine(catalog)
    planner = RoadmapPlanner(catalog, dag)
    return MCPServer(catalog, dag, planner)


def test_calculate_cert_roi(catalog):
    """Test ROI calculations for a known certification."""
    cert = catalog.get("cloud-aws-saa") or catalog.get_all()[0]
    analysis = calculate_cert_roi(cert)

    assert analysis.cert_id == cert.id
    assert analysis.title == cert.title
    assert analysis.annual_salary_premium_usd >= 4000.0
    assert analysis.payback_period_months >= 0.0
    assert analysis.payback_period_months < 12.0  # Typically pays back within a year
    assert analysis.hourly_study_value_usd > 0.0
    assert analysis.five_year_net_gain_usd > 0.0
    assert analysis.five_year_roi_pct > 100.0
    assert analysis.market_demand_rating in ("Very High", "High", "Moderate")

    # Verify serialization
    data = analysis.to_dict()
    assert data["cert_id"] == cert.id
    assert "five_year_roi_pct" in data


def test_calculate_skill_overlap(catalog):
    """Test skill overlap between two related cloud/security certifications."""
    all_certs = catalog.get_all()
    c_a = catalog.get("cloud-aws-saa") or all_certs[0]
    c_b = catalog.get("sec-aws-sec-spec") or all_certs[1]

    overlap = calculate_skill_overlap(c_a, c_b)
    assert overlap.cert_a_id == c_a.id
    assert overlap.cert_b_id == c_b.id
    assert 0.0 <= overlap.overlap_ratio <= 1.0
    assert overlap.synergy_discount_pct >= 0.0
    assert overlap.study_hours_saved >= 0

    data = overlap.to_dict()
    assert "overlap_ratio" in data
    assert "study_hours_saved" in data


def test_evaluate_portfolio(catalog):
    """Test aggregate evaluation of multiple credentials."""
    all_certs = catalog.get_all()
    sample_ids = [c.id for c in all_certs[:4]]

    valuation = evaluate_portfolio(sample_ids, catalog=catalog)
    assert valuation.total_credentials == len(sample_ids)
    assert valuation.total_investment_cost_usd > 0
    assert valuation.total_study_hours_invested > 0
    assert valuation.total_annual_salary_potential_usd > 0
    assert 0.0 <= valuation.composite_marketability_index <= 100.0
    assert 0.0 <= valuation.vendor_diversification_score <= 100.0
    assert 0.0 <= valuation.multi_cloud_score <= 100.0
    assert 0.0 <= valuation.security_quotient <= 100.0
    min_sal, max_sal = valuation.estimated_salary_range_usd
    assert min_sal < max_sal

    data = valuation.to_dict()
    assert data["total_credentials"] == len(sample_ids)
    assert "composite_marketability_index" in data


def test_scorecard_formatters(catalog):
    """Verify ASCII box scorecard formatting functions."""
    cert = catalog.get_all()[0]
    roi = calculate_cert_roi(cert)
    roi_card = format_roi_scorecard(roi)
    assert "CERTIFICATION ROI & COMPENSATION ANALYSIS" in roi_card
    assert cert.title in roi_card

    val = evaluate_portfolio([cert.id], catalog=catalog)
    val_card = format_portfolio_scorecard(val)
    assert "CREDENTIAL PORTFOLIO VALUATION" in val_card


def test_mcp_tool_calculate_roi(mcp_server, catalog):
    """Verify MCP tool certpath_calculate_roi."""
    cert = catalog.get_all()[0]
    req = {
        "jsonrpc": "2.0",
        "id": 201,
        "method": "tools/call",
        "params": {
            "name": "certpath_calculate_roi",
            "arguments": {"cert_id": cert.id, "format": "json"},
        },
    }
    res = mcp_server.handle_request(req)
    assert res is not None
    assert "result" in res
    assert not res["result"].get("isError", False)
    payload = json.loads(res["result"]["content"][0]["text"])
    assert payload["cert_id"] == cert.id
    assert "annual_salary_premium_usd" in payload


def test_mcp_tool_skill_overlap(mcp_server, catalog):
    """Verify MCP tool certpath_skill_overlap."""
    certs = catalog.get_all()[:2]
    req = {
        "jsonrpc": "2.0",
        "id": 202,
        "method": "tools/call",
        "params": {
            "name": "certpath_skill_overlap",
            "arguments": {"cert_a_id": certs[0].id, "cert_b_id": certs[1].id, "format": "json"},
        },
    }
    res = mcp_server.handle_request(req)
    assert res is not None
    assert "result" in res
    assert not res["result"].get("isError", False)
    payload = json.loads(res["result"]["content"][0]["text"])
    assert "overlap_ratio" in payload


def test_mcp_tool_portfolio_valuation(mcp_server, catalog):
    """Verify MCP tool certpath_portfolio_valuation."""
    certs = catalog.get_all()[:3]
    req = {
        "jsonrpc": "2.0",
        "id": 203,
        "method": "tools/call",
        "params": {
            "name": "certpath_portfolio_valuation",
            "arguments": {"cert_ids": [c.id for c in certs], "format": "json"},
        },
    }
    res = mcp_server.handle_request(req)
    assert res is not None
    assert "result" in res
    assert not res["result"].get("isError", False)
    payload = json.loads(res["result"]["content"][0]["text"])
    assert payload["total_credentials"] == 3


def test_cli_subcommand_roi(capsys, catalog):
    """Verify CLI subcommand 'roi' works."""
    cert = catalog.get_all()[0]
    ret = main(["roi", "--cert", cert.id, "--json", "--no-color"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["cert_id"] == cert.id


def test_cli_subcommand_overlap(capsys, catalog):
    """Verify CLI subcommand 'overlap' works."""
    certs = catalog.get_all()[:2]
    ret = main(["overlap", certs[0].id, certs[1].id, "--json", "--no-color"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "overlap_ratio" in data
