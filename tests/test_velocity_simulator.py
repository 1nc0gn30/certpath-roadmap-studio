"""Comprehensive tests for Learning Velocity Simulator & Monte Carlo Engine."""

from __future__ import annotations

import json
import urllib.request
from typing import List

import pytest

from certpath_roadmap_studio.catalog import Certification, CertificationCatalog
from certpath_roadmap_studio.cli import main as cli_main
from certpath_roadmap_studio.dag_engine import DAGEngine
from certpath_roadmap_studio.mcp_server import MCPServer
from certpath_roadmap_studio.roadmap_planner import RoadmapPlan, RoadmapPlanner
from certpath_roadmap_studio.velocity_simulator import (
    ExperienceLevel,
    FatigueWarning,
    MilestoneTimelineItem,
    MonteCarloSummary,
    VelocitySimulationReport,
    calculate_pacing_sensitivity,
    generate_ascii_burndown,
    simulate_velocity,
)


def test_experience_level_properties():
    """Verify experience tier velocity multipliers and pass rates."""
    assert ExperienceLevel.BEGINNER.speed_multiplier < 1.0
    assert ExperienceLevel.INTERMEDIATE.speed_multiplier == 1.0
    assert ExperienceLevel.ADVANCED.speed_multiplier > 1.0
    assert ExperienceLevel.EXPERT.speed_multiplier > ExperienceLevel.ADVANCED.speed_multiplier

    assert ExperienceLevel.BEGINNER.base_pass_rate < ExperienceLevel.INTERMEDIATE.base_pass_rate
    assert ExperienceLevel.ADVANCED.base_pass_rate > ExperienceLevel.INTERMEDIATE.base_pass_rate


def test_simulate_velocity_basic(sample_planner: RoadmapPlanner):
    """Verify basic velocity simulation on a generated roadmap plan."""
    plan = sample_planner.generate_roadmap("cloud_sec_lead", weekly_hours=10)
    report = simulate_velocity(
        plan_or_certs=plan,
        weekly_hours=10.0,
        experience_level=ExperienceLevel.INTERMEDIATE,
        simulation_trials=200,
        random_seed=42,
    )

    assert isinstance(report, VelocitySimulationReport)
    assert report.target_name == plan.target_name
    assert report.experience_level == "intermediate"
    assert report.total_nominal_hours == plan.total_hours
    assert report.total_adjusted_hours > 0
    assert len(report.milestones) == len(plan.all_certifications)
    assert len(report.sensitivity_matrix) > 0
    assert "Burndown Trajectory" in report.ascii_burndown_chart

    # Check first milestone properties
    m1 = report.milestones[0]
    assert isinstance(m1, MilestoneTimelineItem)
    assert m1.index == 1
    assert m1.pass_probability > 0.0
    assert m1.completion_date_iso >= m1.start_date_iso

    # Check serialization
    d = report.to_dict()
    assert "monte_carlo" in d
    assert "milestones" in d
    assert "fatigue_index" in d


def test_fatigue_and_burnout_detection():
    """Verify that multiple consecutive advanced certs trigger burnout warnings."""
    hard_certs = [
        Certification(
            id=f"cert-hard-{i}",
            title=f"Expert Certification {i}",
            provider="Vendor",
            level="Advanced",
            category="Cloud",
            description="Deep advanced exam",
            estimated_hours=140,
            cost_usd=400.0,
        )
        for i in range(1, 4)
    ]

    report = simulate_velocity(
        plan_or_certs=hard_certs,
        weekly_hours=8.0,
        experience_level="beginner",
        simulation_trials=100,
        random_seed=123,
    )

    assert report.fatigue_index > 40.0
    assert len(report.fatigue_warnings) >= 1
    w = report.fatigue_warnings[0]
    assert isinstance(w, FatigueWarning)
    assert w.risk_level in ("MEDIUM", "HIGH", "CRITICAL")
    assert w.consecutive_hard_exams >= 1
    assert "decompression" in w.recommendation.lower() or "rest" in w.recommendation.lower() or "load" in w.recommendation.lower()


def test_monte_carlo_distribution_ordering(real_planner: RoadmapPlanner):
    """Verify Monte Carlo simulation percentiles satisfy P50 <= P80 <= P95."""
    plan = real_planner.generate_roadmap("cloud_security_architect", weekly_hours=15)
    report = simulate_velocity(
        plan_or_certs=plan,
        weekly_hours=15.0,
        experience_level="advanced",
        simulation_trials=300,
        random_seed=999,
    )

    mc = report.monte_carlo
    assert isinstance(mc, MonteCarloSummary)
    assert mc.trials_count == 300
    assert mc.weeks_p50 <= mc.weeks_p80 <= mc.weeks_p95
    assert mc.cost_p50 <= mc.cost_p80 <= mc.cost_p95
    assert mc.completion_date_p50 <= mc.completion_date_p80 <= mc.completion_date_p95
    assert mc.retakes_p50 <= mc.retakes_p95


def test_pacing_sensitivity_matrix(sample_planner: RoadmapPlanner):
    """Verify pacing sensitivity calculates inversely proportional durations."""
    plan = sample_planner.generate_roadmap("cloud_sec_lead")
    matrix = calculate_pacing_sensitivity(plan, hours_options=[5, 10, 20])

    assert len(matrix) == 3
    # 20 hrs/week should finish faster than 5 hrs/week
    w_5 = next(item["estimated_weeks"] for item in matrix if item["weekly_hours"] == 5)
    w_20 = next(item["estimated_weeks"] for item in matrix if item["weekly_hours"] == 20)
    assert w_20 < w_5


def test_ascii_burndown_chart():
    """Verify ASCII burndown chart generation."""
    chart = generate_ascii_burndown(total_hours=120, weekly_hours=10, total_weeks=12.0)
    assert "Burndown" in chart
    assert "100.0%" in chart
    assert "W00.0" in chart or "W0.0" in chart


def test_mcp_tool_simulate_velocity(sample_planner: RoadmapPlanner, temp_catalog: CertificationCatalog, sample_dag: DAGEngine):
    """Verify invoking the MCP certpath_simulate_velocity tool."""
    server = MCPServer(temp_catalog, sample_dag, sample_planner)

    req = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "certpath_simulate_velocity",
            "arguments": {
                "target": "cloud_sec_lead",
                "weekly_hours": 12.0,
                "experience_level": "intermediate",
                "trials": 100,
                "format": "json",
            },
        },
    }
    resp = server.handle_request(req)
    assert resp is not None
    assert "result" in resp
    assert not resp["result"].get("isError")

    raw_text = resp["result"]["content"][0]["text"]
    parsed = json.loads(raw_text)
    assert parsed["target_name"] == "Cloud Security Lead"
    assert "monte_carlo" in parsed

    # Markdown format call
    req_md = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {
            "name": "certpath_simulate_velocity",
            "arguments": {
                "target": "cloud_sec_lead",
                "format": "markdown",
            },
        },
    }
    resp_md = server.handle_request(req_md)
    assert "Monte Carlo" in resp_md["result"]["content"][0]["text"]


def test_ui_api_simulate_velocity_endpoints(test_server):
    """Verify /api/simulate-velocity GET and POST endpoints."""
    base_url, _ = test_server

    # 1. GET /api/simulate-velocity
    get_url = f"{base_url}/api/simulate-velocity?target=cloud_sec_lead&hours=15&experience_level=advanced&trials=100"
    with urllib.request.urlopen(get_url) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "monte_carlo" in data
        assert data["weekly_hours"] == 15.0

    # 2. POST /api/simulate-velocity
    post_url = f"{base_url}/api/simulate-velocity"
    body = json.dumps({
        "target": "cloud_sec_lead",
        "weekly_hours": 12.0,
        "experience_level": "beginner",
        "trials": 100,
    }).encode("utf-8")
    req = urllib.request.Request(post_url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "monte_carlo" in data
        assert data["experience_level"] == "beginner"


def test_cli_simulate_command(capsys):
    """Verify CLI 'simulate' command execution."""
    code = cli_main(["simulate", "--role", "cloud_security_architect", "--hours", "15", "--trials", "100", "--json"])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "monte_carlo" in data
    assert data["target_name"] == "Cloud Security Architect"

    # Human-readable table run
    code_text = cli_main(["simulate", "--role", "cloud_security_architect", "--trials", "50"])
    assert code_text == 0
    captured_text = capsys.readouterr()
    assert "Monte Carlo Probabilistic Completion Milestones" in captured_text.out
    assert "Milestone Study Timeline Sequence" in captured_text.out
