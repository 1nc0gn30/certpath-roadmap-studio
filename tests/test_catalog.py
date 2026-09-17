"""Tests for certification models and catalog management in catalog.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from certpath_roadmap_studio.catalog import (
    Certification,
    CertificationCatalog,
    CertificationResource,
)


def test_certification_resource_serialization():
    """Verify CertificationResource serialization to and from dictionary."""
    res = CertificationResource(
        title="Official AWS Guide",
        url="https://aws.amazon.com/certification",
        type="Official",
    )
    d = res.to_dict()
    assert d["title"] == "Official AWS Guide"
    assert d["url"] == "https://aws.amazon.com/certification"
    assert d["type"] == "Official"

    res_back = CertificationResource.from_dict(d)
    assert res_back.title == res.title
    assert res_back.url == res.url
    assert res_back.type == res.type


def test_certification_dataclass_methods():
    """Verify Certification creation, serialization, and camelCase/snake_case conversion."""
    cert = Certification(
        id="test-cloud-sec",
        title="Test Cloud Security Specialist",
        provider="TestCloud",
        level="Intermediate",
        category="Cloud Computing",
        description="Comprehensive cloud security certification test.",
        skills_gained=["Cloud Security", "IAM", "Encryption"],
        prerequisites=["test-cloud-foundations"],
        next_steps=["test-cloud-expert"],
        link="https://example.com/test-cloud-sec",
        color="#3b82f6",
        resources=[CertificationResource(title="Prep Course", url="https://example.com/prep", type="Course")],
        interests=["cloud", "security"],
        estimated_hours=80,
        cost_usd=200.0,
        exam_code="TCS-100",
    )

    # Snake case dictionary
    snake_d = cert.to_dict(camel_case=False)
    assert snake_d["id"] == "test-cloud-sec"
    assert "skills_gained" in snake_d
    assert "estimated_hours" in snake_d
    assert snake_d["cost_usd"] == 200.0

    # Camel case dictionary
    camel_d = cert.to_dict(camel_case=True)
    assert camel_d["id"] == "test-cloud-sec"
    assert "skillsGained" in camel_d
    assert "estimatedHours" in camel_d
    assert camel_d["costUsd"] == 200.0

    # Construct back from camelCase dictionary
    reconstructed = Certification.from_dict(camel_d)
    assert reconstructed.id == cert.id
    assert reconstructed.title == cert.title
    assert reconstructed.skills_gained == cert.skills_gained
    assert reconstructed.estimated_hours == 80
    assert reconstructed.cost_usd == 200.0
    assert reconstructed.exam_code == "TCS-100"


def test_real_catalog_loading_and_telemetry(real_catalog: CertificationCatalog):
    """Verify loading real 137 certs dataset with categories and telemetry."""
    assert len(real_catalog) >= 130
    assert len(real_catalog.get_all()) == len(real_catalog)

    categories = real_catalog.get_categories()
    assert "Cloud Computing" in categories
    assert "Cyber Security" in categories
    assert "AI Development" in categories
    assert len(categories) == 7

    providers = real_catalog.get_providers()
    assert len(providers) >= 20
    assert any("Amazon" in p or "AWS" in p for p in providers)
    assert any("Microsoft" in p or "Azure" in p for p in providers)
    assert any("Google" in p for p in providers)
    assert any("CompTIA" in p for p in providers)


def test_catalog_search_filters(real_catalog: CertificationCatalog):
    """Verify multi-criteria search in the catalog."""
    # Search by keyword
    aws_certs = real_catalog.search(query="AWS")
    assert len(aws_certs) > 0
    assert all("AWS" in c.title or "AWS" in c.provider or "Amazon" in c.provider or "AWS" in c.description for c in aws_certs)

    # Search by level
    entry_certs = real_catalog.search(level="Entry")
    assert len(entry_certs) > 0
    assert all(c.level.lower() == "entry" for c in entry_certs)

    # Search by category
    sec_certs = real_catalog.search(category="Cyber Security")
    assert len(sec_certs) >= 20
    assert all(c.category == "Cyber Security" for c in sec_certs)

    # Search by skill
    k8s_certs = real_catalog.search(skill="Kubernetes")
    assert len(k8s_certs) > 0
    assert all(any("kubernetes" in s.lower() for s in c.skills_gained) for c in k8s_certs)


def test_catalog_get_by_id_and_contains(temp_catalog: CertificationCatalog):
    """Verify get_by_id lookup and in-operator membership."""
    cert = temp_catalog.get_by_id("cert-entry-1")
    assert cert is not None
    assert cert.title == "Foundations of Cloud Computing"
    assert "cert-entry-1" in temp_catalog

    missing = temp_catalog.get_by_id("non-existent-cert-id")
    assert missing is None
    assert "non-existent-cert-id" not in temp_catalog


def test_catalog_add_certification(temp_catalog: CertificationCatalog):
    """Verify dynamically adding new certifications to catalog."""
    initial_count = len(temp_catalog)
    new_cert = Certification(
        id="cert-custom-99",
        title="Advanced Rust Security Engineer",
        provider="RustFoundation",
        level="Advanced",
        category="Software Development",
        description="Memory safety, concurrency, and audit of Rust systems.",
        skills_gained=["Rust", "Memory Safety", "Cryptography"],
        prerequisites=["cert-entry-1"],
        next_steps=[],
        link="https://example.com/rust",
        color="#f97316",
        resources=[],
        interests=["rust", "security"],
        estimated_hours=120,
        cost_usd=250.0,
    )

    temp_catalog.add_certification(new_cert)
    assert len(temp_catalog) == initial_count + 1
    assert temp_catalog.get_by_id("cert-custom-99") == new_cert


def test_catalog_summary_statistics(temp_catalog: CertificationCatalog):
    """Verify aggregated catalog statistics generation."""
    stats = temp_catalog.summary_statistics()
    assert stats["total_certs"] == 5
    assert stats["total_skills"] > 10
    assert stats["average_hours"] > 0
    assert stats["average_cost"] > 0
    assert "by_category" in stats
    assert "by_provider" in stats
    assert "by_level" in stats
