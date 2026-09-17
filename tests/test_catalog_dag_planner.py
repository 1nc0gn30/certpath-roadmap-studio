"""Unit test suite for CertPath Roadmap Studio core catalog, DAG engine, roadmap planner, and exporters."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure src is on Python path
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from certpath_roadmap_studio.catalog import (
    Certification,
    CertificationCatalog,
    CertificationResource,
)
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
from certpath_roadmap_studio.dag_engine import DAGEngine
from certpath_roadmap_studio.matrix_exporter import (
    export_ascii_tree,
    export_json_ld,
    export_markdown,
    export_mermaid,
)
from certpath_roadmap_studio.roadmap_planner import (
    BUILTIN_ROLES,
    CareerRole,
    RoadmapPlanner,
)


class TestCompat(unittest.TestCase):
    """Test cross-platform compatibility helper functions."""

    def test_platform_detection(self):
        # Ensure platform boolean functions return boolean
        self.assertIsInstance(is_windows(), bool)
        self.assertIsInstance(is_macos(), bool)
        self.assertIsInstance(is_linux(), bool)
        self.assertIsInstance(is_termux(), bool)
        self.assertIsInstance(get_platform_name(), str)

    def test_normalize_path(self):
        p = normalize_path(".")
        self.assertTrue(p.is_absolute())
        with self.assertRaises(ValueError):
            normalize_path(None)

    def test_safe_resolve_path(self):
        base = normalize_path(".")
        rel = "src/certpath_roadmap_studio"
        resolved = safe_resolve_path(rel, base)
        self.assertTrue(resolved.is_absolute())

    def test_ensure_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_sub = Path(tmpdir) / "nested" / "dir"
            out = ensure_directory(test_sub)
            self.assertTrue(out.exists())
            self.assertTrue(out.is_dir())

    def test_atomic_write_and_read_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            content = "Hello, CertPath! \U0001F680"
            written = atomic_write_text(test_file, content)
            self.assertGreater(written, 0)
            read_back = read_text_safe(test_file)
            self.assertEqual(read_back, content)

    def test_atomic_write_and_read_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.json"
            data = {"app": "certpath", "version": 1, "certs": ["a+", "sec+"]}
            atomic_write_json(test_file, data)
            loaded = read_json_safe(test_file)
            self.assertEqual(loaded, data)

    def test_read_text_fallback_default(self):
        non_existent = Path("/non/existent/path/for/certpath/test.txt")
        result = read_text_safe(non_existent, default="fallback_val")
        self.assertEqual(result, "fallback_val")


class TestCatalog(unittest.TestCase):
    """Test certification catalog data models, loading, searching, and statistics."""

    def setUp(self):
        self.catalog = CertificationCatalog()

    def test_catalog_loaded_data(self):
        self.assertGreaterEqual(len(self.catalog), 130)
        self.assertIn("cyber-sec-plus", self.catalog)

    def test_certification_dataclass_camel_and_snake_case(self):
        raw_camel = {
            "id": "test-cert",
            "title": "Test Cloud Certification",
            "provider": "AWS",
            "level": "Associate",
            "category": "Cloud Computing",
            "description": "Comprehensive test cert.",
            "skillsGained": ["VPC", "EC2"],
            "prerequisites": ["aws-cloud-practitioner"],
            "nextSteps": ["aws-pro"],
            "interests": ["cloud"],
            "resources": [{"title": "Docs", "url": "https://aws.amazon.com", "type": "Official"}],
        }
        cert = Certification.from_dict(raw_camel)
        self.assertEqual(cert.id, "test-cert")
        self.assertEqual(cert.skills_gained, ["VPC", "EC2"])
        self.assertEqual(cert.prerequisites, ["aws-cloud-practitioner"])
        self.assertEqual(cert.next_steps, ["aws-pro"])
        self.assertEqual(len(cert.resources), 1)
        self.assertEqual(cert.resources[0].type, "Official")

        dict_out = cert.to_dict(camel_case=True)
        self.assertIn("skillsGained", dict_out)
        self.assertIn("nextSteps", dict_out)

    def test_search_and_filtering(self):
        aws_certs = self.catalog.search(provider="Amazon Web Services")
        self.assertGreater(len(aws_certs), 0)
        for c in aws_certs:
            self.assertIn("amazon", c.provider.lower())

        sec_certs = self.catalog.search(category="Cyber Security")
        self.assertGreater(len(sec_certs), 0)

        entry_certs = self.catalog.search(level="Entry")
        self.assertGreater(len(entry_certs), 0)

        query_certs = self.catalog.search(query="Python")
        self.assertGreater(len(query_certs), 0)

    def test_summary_statistics(self):
        stats = self.catalog.summary_statistics()
        self.assertIn("total_certs", stats)
        self.assertIn("by_category", stats)
        self.assertIn("by_provider", stats)
        self.assertIn("by_level", stats)
        self.assertIn("average_hours", stats)
        self.assertIn("average_cost", stats)
        self.assertGreater(stats["total_certs"], 0)
        self.assertGreater(stats["average_hours"], 0)

    def test_categories_and_providers_lists(self):
        cats = self.catalog.get_categories()
        self.assertIsInstance(cats, list)
        self.assertIn("Cyber Security", cats)
        self.assertIn("Cloud Computing", cats)

        provs = self.catalog.get_providers()
        self.assertIsInstance(provs, list)
        self.assertIn("CompTIA", provs)


class TestDAGEngine(unittest.TestCase):
    """Test DAG solver, prerequisite resolution, topological sort, paths, and difficulty scoring."""

    def setUp(self):
        self.catalog = CertificationCatalog()
        self.dag = DAGEngine(self.catalog)

    def test_dag_acyclic(self):
        self.assertTrue(self.dag.is_dag())
        self.assertEqual(self.dag.detect_cycles(), [])

    def test_resolve_prerequisites(self):
        # CISSP has deep prerequisites
        prereqs = self.dag.resolve_prerequisites("cyber-cissp", include_target=True)
        self.assertGreater(len(prereqs), 5)
        prereq_ids = [c.id for c in prereqs]
        self.assertIn("cyber-sec-plus", prereq_ids)
        self.assertEqual(prereqs[-1].id, "cyber-cissp")

    def test_resolve_dependents(self):
        dependents = self.dag.resolve_dependents("soft-comptia-network-plus")
        self.assertGreater(len(dependents), 5)
        dep_ids = [c.id for c in dependents]
        self.assertIn("cyber-sec-plus", dep_ids)

    def test_topological_sort(self):
        topo = self.dag.get_topological_sort()
        self.assertEqual(len(topo), len(self.catalog))
        # Verify prerequisite ordering: every prerequisite appears before its dependent
        id_to_idx = {c.id: i for i, c in enumerate(topo)}
        for c in topo:
            for p in c.prerequisites:
                if p in id_to_idx:
                    self.assertLess(id_to_idx[p], id_to_idx[c.id])

    def test_find_shortest_path(self):
        path = self.dag.find_shortest_path("soft-comptia-a-plus", "cyber-cissp")
        self.assertIsNotNone(path)
        self.assertEqual(path[0].id, "soft-comptia-a-plus")
        self.assertEqual(path[-1].id, "cyber-cissp")

    def test_calculate_critical_path(self):
        crit = self.dag.calculate_critical_path("cyber-cissp", metric="hours")
        self.assertGreater(len(crit), 3)
        self.assertEqual(crit[-1].id, "cyber-cissp")

    def test_difficulty_score(self):
        entry_score = self.dag.difficulty_score("cyber-isc2-cc")
        adv_score = self.dag.difficulty_score("cyber-cissp")
        self.assertGreater(adv_score, entry_score)

    def test_roots_and_leaves(self):
        roots = self.dag.get_roots()
        leaves = self.dag.get_leaves()
        self.assertGreater(len(roots), 0)
        self.assertGreater(len(leaves), 0)


class TestRoadmapPlanner(unittest.TestCase):
    """Test personalized career roadmap generation, phase partitioning, and skill gap analysis."""

    def setUp(self):
        self.catalog = CertificationCatalog()
        self.dag = DAGEngine(self.catalog)
        self.planner = RoadmapPlanner(self.catalog, self.dag)

    def test_builtin_roles(self):
        roles = self.planner.get_roles()
        role_ids = [r.role_id for r in roles]
        self.assertIn("cloud_security_architect", role_ids)
        self.assertIn("ai_ml_engineer", role_ids)
        self.assertIn("fullstack_devops_lead", role_ids)
        self.assertIn("penetration_tester", role_ids)
        self.assertIn("data_platform_architect", role_ids)
        self.assertIn("soc_analyst", role_ids)

    def test_generate_roadmap_role(self):
        plan = self.planner.generate_roadmap(
            "penetration_tester",
            weekly_hours=12,
            max_budget=3000.0,
        )
        self.assertEqual(plan.target_name, "Offensive Security & Penetration Tester")
        self.assertEqual(plan.target_type, "role")
        self.assertGreater(len(plan.phases), 0)
        self.assertGreater(len(plan.all_certifications), 0)
        self.assertGreater(plan.total_hours, 0)
        self.assertGreater(plan.total_weeks, 0)
        self.assertGreater(len(plan.milestones), 0)
        self.assertGreater(len(plan.skills_progression), 0)

    def test_generate_roadmap_with_acquired_certs(self):
        plan_all = self.planner.generate_roadmap("penetration_tester")
        plan_with_acquired = self.planner.generate_roadmap(
            "penetration_tester",
            current_certs=["soft-comptia-a-plus", "soft-comptia-network-plus", "cyber-sec-plus"],
        )
        self.assertLess(len(plan_with_acquired.all_certifications), len(plan_all.all_certifications))
        self.assertLess(plan_with_acquired.total_hours, plan_all.total_hours)

    def test_skill_gap_analysis(self):
        gap = self.planner.skill_gap_analysis(
            "soc_analyst",
            acquired_skills=["Networking Fundamentals"],
            current_certs=["soft-comptia-network-plus"],
        )
        self.assertIsInstance(gap.match_percentage, float)
        self.assertGreater(len(gap.missing_skills), 0)
        self.assertGreater(len(gap.recommended_certs), 0)


class TestMatrixExporter(unittest.TestCase):
    """Test Mermaid, Markdown, ASCII tree, and JSON-LD visual matrix exporters."""

    def setUp(self):
        self.catalog = CertificationCatalog()
        self.dag = DAGEngine(self.catalog)
        self.planner = RoadmapPlanner(self.catalog, self.dag)
        self.plan = self.planner.generate_roadmap("soc_analyst", weekly_hours=10)

    def test_export_mermaid(self):
        mermaid_out = export_mermaid(self.plan, direction="LR")
        self.assertTrue(mermaid_out.startswith("flowchart LR"))
        self.assertIn("subgraph", mermaid_out)
        self.assertIn("style ", mermaid_out)

    def test_export_markdown(self):
        md_out = export_markdown(self.plan)
        self.assertIn("# 🗺️", md_out)
        self.assertIn("Executive Summary & Metrics", md_out)
        self.assertIn("- [ ] **Milestone", md_out)
        self.assertIn("Comprehensive Skill Progression", md_out)

    def test_export_ascii_tree(self):
        tree_out = export_ascii_tree("cyber-cysa-plus", self.catalog, self.dag)
        self.assertIn("🎯 Target:", tree_out)
        self.assertIn("Prerequisite Hierarchy", tree_out)

    def test_export_json_ld_cert(self):
        cert = self.catalog.get_by_id("cyber-cysa-plus")
        json_ld = export_json_ld(cert)
        parsed = json.loads(json_ld)
        self.assertEqual(parsed["@context"], "https://schema.org")
        self.assertEqual(parsed["@type"], "EducationalOccupationalCredential")
        self.assertEqual(parsed["name"], cert.title)

    def test_export_json_ld_roadmap(self):
        json_ld = export_json_ld(self.plan)
        parsed = json.loads(json_ld)
        self.assertEqual(parsed["@context"], "https://schema.org")
        self.assertEqual(parsed["@type"], "EducationalOccupationalProgram")
        self.assertIn("hasCourse", parsed)


if __name__ == "__main__":
    unittest.main()
