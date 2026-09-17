"""Tests for visual matrix, Mermaid DAG, Markdown, ASCII, and JSON-LD exporters in matrix_exporter.py."""

from __future__ import annotations

import json

import pytest

from certpath_roadmap_studio.matrix_exporter import (
    export_ascii_tree,
    export_json_ld,
    export_markdown,
    export_mermaid,
)
from certpath_roadmap_studio.roadmap_planner import RoadmapPlanner


def test_export_mermaid_with_roadmap_plan(sample_planner: RoadmapPlanner):
    """Verify exporting RoadmapPlan to valid Mermaid flowchart syntax."""
    plan = sample_planner.generate_roadmap("cloud_sec_lead")
    mermaid = export_mermaid(plan, direction="LR")

    assert "flowchart LR" in mermaid or "graph LR" in mermaid
    assert "subgraph" in mermaid
    assert "-->" in mermaid
    assert "style " in mermaid


def test_export_mermaid_with_cert_list(temp_catalog):
    """Verify exporting certification list to Mermaid flowchart with categories."""
    certs = temp_catalog.get_all()
    mermaid_cat = export_mermaid(certs, group_by="category", direction="TD")

    assert "flowchart TD" in mermaid_cat or "graph TD" in mermaid_cat
    assert "subgraph" in mermaid_cat
    assert "cert_entry_1" in mermaid_cat or "cert-entry-1" in mermaid_cat or "n_cert" in mermaid_cat


def test_export_markdown_study_guide(sample_planner: RoadmapPlanner):
    """Verify Markdown study guide generation with milestones and checklist."""
    plan = sample_planner.generate_roadmap("cloud_sec_lead", weekly_hours=10)
    md = export_markdown(plan, include_resources=True)

    assert "# 🗺️" in md or "Cloud Security Lead" in md
    assert "Milestone Checklist" in md
    assert "- [ ]" in md
    assert "## 🧠 Comprehensive Skill Progression" in md
    assert "## 💡 Proven Exam Preparation Strategy" in md


def test_export_ascii_tree(temp_catalog, sample_dag):
    """Verify ASCII prerequisite and unlock progression tree."""
    tree = export_ascii_tree("cert-adv-1", catalog=temp_catalog, dag_engine=sample_dag)

    assert "🎯 Target:" in tree
    assert "Prerequisite Hierarchy" in tree
    assert "cert-adv-1" in tree

    # Missing cert ID
    missing_tree = export_ascii_tree("missing-cert", catalog=temp_catalog, dag_engine=sample_dag)
    assert "not found" in missing_tree.lower()


def test_export_json_ld_credential_and_program(temp_catalog, sample_planner: RoadmapPlanner):
    """Verify Schema.org EducationalOccupationalCredential and Program JSON-LD."""
    # Single cert JSON-LD
    cert = temp_catalog.get_by_id("cert-adv-1")
    assert cert is not None
    json_ld_cert = export_json_ld(cert)
    parsed_cert = json.loads(json_ld_cert)
    assert parsed_cert["@context"] == "https://schema.org"
    assert parsed_cert["@type"] == "EducationalOccupationalCredential"
    assert parsed_cert["name"] == cert.title

    # Roadmap Program JSON-LD
    plan = sample_planner.generate_roadmap("cloud_sec_lead")
    json_ld_plan = export_json_ld(plan)
    parsed_plan = json.loads(json_ld_plan)
    assert parsed_plan["@context"] == "https://schema.org"
    assert parsed_plan["@type"] == "EducationalOccupationalProgram"
    assert "hasCourse" in parsed_plan
