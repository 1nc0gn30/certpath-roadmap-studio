"""Pytest configuration and shared fixtures for CertPath Roadmap Studio tests."""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Tuple

# Ensure src/ is importable
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest

from certpath_roadmap_studio.catalog import Certification, CertificationCatalog, CertificationResource
from certpath_roadmap_studio.dag_engine import DAGEngine
from certpath_roadmap_studio.roadmap_planner import CareerRole, RoadmapPlanner
from certpath_roadmap_studio.ui_server import create_server


@pytest.fixture
def sample_certs_dict() -> List[Dict[str, Any]]:
    """Return a small, clean, controlled set of certification dictionaries."""
    return [
        {
            "id": "cert-entry-1",
            "title": "Foundations of Cloud Computing",
            "provider": "CloudAcademy",
            "level": "Entry",
            "category": "Cloud Computing",
            "description": "Fundamental concepts of cloud computing, storage, and networking.",
            "skillsGained": ["Cloud Fundamentals", "Object Storage", "Virtual Machines"],
            "prerequisites": [],
            "nextSteps": ["cert-inter-1", "cert-inter-2"],
            "link": "https://example.com/cert-entry-1",
            "color": "#34a853",
            "resources": [
                {"title": "Official Study Guide", "url": "https://example.com/guide1", "type": "Official"}
            ],
            "interests": ["cloud", "infrastructure"],
            "estimatedHours": 40,
            "costUsd": 99.0,
            "examCode": "CLD-101",
        },
        {
            "id": "cert-entry-2",
            "title": "Networking Basics",
            "provider": "NetAcademy",
            "level": "Entry",
            "category": "Cyber Security",
            "description": "TCP/IP, subnetting, DNS, and OSI model essentials.",
            "skillsGained": ["TCP/IP", "DNS", "Routing", "Subnetting"],
            "prerequisites": [],
            "nextSteps": ["cert-inter-2"],
            "link": "https://example.com/cert-entry-2",
            "color": "#4285f4",
            "resources": [],
            "interests": ["networking", "security"],
            "estimatedHours": 50,
            "costUsd": 125.0,
            "examCode": "NET-001",
        },
        {
            "id": "cert-inter-1",
            "title": "Cloud Solutions Architect",
            "provider": "CloudAcademy",
            "level": "Intermediate",
            "category": "Cloud Computing",
            "description": "Architecting resilient, secure, high-availability cloud solutions.",
            "skillsGained": ["Cloud Architecture", "High Availability", "VPC Peering", "IAM Policies"],
            "prerequisites": ["cert-entry-1"],
            "nextSteps": ["cert-adv-1"],
            "link": "https://example.com/cert-inter-1",
            "color": "#fbbc04",
            "resources": [
                {"title": "Architecture Deep Dive", "url": "https://example.com/arch", "type": "Course"}
            ],
            "interests": ["cloud", "architecture"],
            "estimatedHours": 80,
            "costUsd": 150.0,
            "examCode": "CLD-201",
        },
        {
            "id": "cert-inter-2",
            "title": "Security Practitioner",
            "provider": "SecOrg",
            "level": "Intermediate",
            "category": "Cyber Security",
            "description": "Applied cryptography, firewall configuration, and vulnerability scanning.",
            "skillsGained": ["Cryptography", "Firewalls", "Vulnerability Scanning", "Threat Modeling"],
            "prerequisites": ["cert-entry-1", "cert-entry-2"],
            "nextSteps": ["cert-adv-1"],
            "link": "https://example.com/cert-inter-2",
            "color": "#ea4335",
            "resources": [],
            "interests": ["security", "crypto"],
            "estimatedHours": 90,
            "costUsd": 250.0,
            "examCode": "SEC-202",
        },
        {
            "id": "cert-adv-1",
            "title": "Enterprise Cloud Security Principal",
            "provider": "CloudAcademy",
            "level": "Advanced",
            "category": "Cyber Security",
            "description": "Zero trust architecture, automated compliance, and enterprise cloud protection.",
            "skillsGained": ["Zero Trust", "KMS Encryption", "SIEM Integration", "Enterprise Governance"],
            "prerequisites": ["cert-inter-1", "cert-inter-2"],
            "nextSteps": [],
            "link": "https://example.com/cert-adv-1",
            "color": "#9334e6",
            "resources": [
                {"title": "Zero Trust Whitepaper", "url": "https://example.com/zt", "type": "Documentation"}
            ],
            "interests": ["cloud-security", "zero-trust", "governance"],
            "estimatedHours": 140,
            "costUsd": 350.0,
            "examCode": "PRIN-301",
        },
    ]


@pytest.fixture
def temp_catalog(sample_certs_dict: List[Dict[str, Any]], tmp_path: Path) -> CertificationCatalog:
    """Return a CertificationCatalog populated with the controlled sample certs."""
    json_path = tmp_path / "test_certs.json"
    json_path.write_text(json.dumps(sample_certs_dict), encoding="utf-8")
    return CertificationCatalog(data_path=json_path)


@pytest.fixture
def real_catalog() -> CertificationCatalog:
    """Return the real full CertificationCatalog with 137+ built-in certifications."""
    return CertificationCatalog()


@pytest.fixture
def sample_dag(temp_catalog: CertificationCatalog) -> DAGEngine:
    """Return DAGEngine initialized with the sample catalog."""
    return DAGEngine(temp_catalog)


@pytest.fixture
def real_dag(real_catalog: CertificationCatalog) -> DAGEngine:
    """Return DAGEngine initialized with the real full catalog."""
    return DAGEngine(real_catalog)


@pytest.fixture
def sample_planner(temp_catalog: CertificationCatalog, sample_dag: DAGEngine) -> RoadmapPlanner:
    """Return RoadmapPlanner initialized with sample catalog and DAG."""
    planner = RoadmapPlanner(temp_catalog, sample_dag)
    custom_role = CareerRole(
        role_id="cloud_sec_lead",
        title="Cloud Security Lead",
        description="Lead enterprise cloud and security architecture.",
        category="Cyber Security",
        target_certs=["cert-adv-1"],
        key_skills=["Zero Trust", "Cloud Architecture"],
        target_level="Advanced",
    )
    planner.register_role(custom_role)
    return planner


@pytest.fixture
def real_planner(real_catalog: CertificationCatalog, real_dag: DAGEngine) -> RoadmapPlanner:
    """Return RoadmapPlanner initialized with real catalog and DAG."""
    return RoadmapPlanner(real_catalog, real_dag)


def get_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def test_server(
    temp_catalog: CertificationCatalog,
    sample_dag: DAGEngine,
    sample_planner: RoadmapPlanner,
    tmp_path: Path,
) -> Generator[Tuple[str, int], None, None]:
    """Launch a live test HTTP server on a random free port and yield (base_url, port)."""
    port = get_free_port()
    host = "127.0.0.1"

    # Create dummy public dir with index.html and certs.json
    pub_dir = tmp_path / "public"
    pub_dir.mkdir(parents=True, exist_ok=True)
    (pub_dir / "index.html").write_text("<!DOCTYPE html><html><body>Test UI</body></html>", encoding="utf-8")
    (pub_dir / "certs.json").write_text(json.dumps([c.to_dict(camel_case=True) for c in temp_catalog.get_all()]), encoding="utf-8")

    server = create_server(
        host=host,
        port=port,
        catalog=temp_catalog,
        dag=sample_dag,
        planner=sample_planner,
        public_dir=pub_dir,
    )

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)

    base_url = f"http://{host}:{port}"
    yield base_url, port

    server.shutdown()
    server.server_close()
    thread.join(timeout=1.0)
