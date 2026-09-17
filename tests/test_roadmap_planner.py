"""Tests for personalized career roadmap planning and skill gap analysis in roadmap_planner.py."""

from __future__ import annotations

import pytest

from certpath_roadmap_studio.roadmap_planner import (
    BUILTIN_ROLES,
    CareerRole,
    RoadmapPlan,
    RoadmapPlanner,
    SkillGapResult,
)


def test_builtin_career_roles(real_planner: RoadmapPlanner):
    """Verify built-in industry-aligned career roles are registered."""
    roles = real_planner.get_roles()
    assert len(roles) >= 6
    role_ids = {r.role_id for r in roles}

    assert "cloud_security_architect" in role_ids
    assert "ai_ml_engineer" in role_ids
    assert "fullstack_devops_lead" in role_ids
    assert "penetration_tester" in role_ids
    assert "data_platform_architect" in role_ids
    assert "soc_analyst" in role_ids

    # Role detail inspection
    sec_arch = real_planner.get_role("cloud_security_architect")
    assert sec_arch is not None
    assert sec_arch.title == "Cloud Security Architect"
    assert len(sec_arch.target_certs) > 0
    assert len(sec_arch.key_skills) > 0


def test_generate_roadmap_for_role(sample_planner: RoadmapPlanner):
    """Verify roadmap plan generation for a target career role."""
    plan = sample_planner.generate_roadmap(
        target_role_or_cert="cloud_sec_lead",
        weekly_hours=10,
        max_budget=1000.0,
    )

    assert isinstance(plan, RoadmapPlan)
    assert plan.target_name == "Cloud Security Lead"
    assert plan.target_type == "role"
    assert plan.weekly_hours == 10
    assert plan.total_hours > 0
    assert plan.total_weeks == round(plan.total_hours / 10, 1)
    assert plan.total_cost_usd > 0
    assert len(plan.phases) > 0
    assert len(plan.milestones) > 0
    assert len(plan.skills_progression) > 0

    # Serialization test
    d = plan.to_dict()
    assert d["target_name"] == "Cloud Security Lead"
    assert "phases" in d
    assert "milestones" in d
    assert "skills_progression" in d


def test_generate_roadmap_skipping_current_certs(sample_planner: RoadmapPlanner):
    """Verify roadmap skips already possessed certifications."""
    # Without current certs
    plan_full = sample_planner.generate_roadmap(
        target_role_or_cert="cloud_sec_lead",
        current_certs=[],
    )
    full_count = len(plan_full.all_certifications)

    # With entry cert already possessed
    plan_partial = sample_planner.generate_roadmap(
        target_role_or_cert="cloud_sec_lead",
        current_certs=["cert-entry-1"],
    )
    partial_count = len(plan_partial.all_certifications)

    assert partial_count < full_count
    assert "cert-entry-1" not in [c.id for c in plan_partial.all_certifications]
    assert plan_partial.total_hours < plan_full.total_hours


def test_generate_roadmap_for_single_cert(sample_planner: RoadmapPlanner):
    """Verify roadmap plan generation for a specific target certification."""
    plan = sample_planner.generate_roadmap("cert-adv-1", weekly_hours=15)
    assert plan.target_type == "certification"
    assert plan.target_cert is not None
    assert plan.target_cert.id == "cert-adv-1"
    assert plan.weekly_hours == 15
    assert len(plan.all_certifications) > 0
    assert plan.all_certifications[-1].id == "cert-adv-1"


def test_skill_gap_analysis(sample_planner: RoadmapPlanner):
    """Verify skill gap comparison against candidate skills and certifications."""
    gap: SkillGapResult = sample_planner.skill_gap_analysis(
        target_role_or_cert="cloud_sec_lead",
        acquired_skills=["Cloud Fundamentals", "Object Storage"],
        current_certs=["cert-entry-1"],
    )

    assert isinstance(gap, SkillGapResult)
    assert gap.match_percentage >= 0.0
    assert len(gap.target_skills) > 0
    assert len(gap.missing_skills) > 0
    assert len(gap.recommended_certs) > 0
    assert "Zero Trust" in gap.missing_skills or "Cloud Architecture" in gap.missing_skills


def test_register_custom_role(sample_planner: RoadmapPlanner):
    """Verify dynamic registration of custom career role archetypes."""
    custom = CareerRole(
        role_id="custom_ai_sec",
        title="AI Security Specialist",
        description="Securing LLMs against adversarial attacks.",
        category="Cyber Security",
        target_certs=["cert-adv-1"],
        key_skills=["Adversarial Robustness", "Model Alignment"],
        target_level="Advanced",
    )
    sample_planner.register_role(custom)
    retrieved = sample_planner.get_role("custom_ai_sec")
    assert retrieved is not None
    assert retrieved.title == "AI Security Specialist"
