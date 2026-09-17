"""Tests for Directed Acyclic Graph (DAG) solver and dependency algorithms in dag_engine.py."""

from __future__ import annotations

import pytest

from certpath_roadmap_studio.catalog import Certification, CertificationCatalog
from certpath_roadmap_studio.dag_engine import DAGEngine


def test_real_dataset_is_acyclic(real_dag: DAGEngine):
    """Verify the real production certification catalog is a strictly acyclic DAG."""
    cycles = real_dag.detect_cycles()
    assert len(cycles) == 0, f"Detected cyclic dependency in production dataset: {cycles}"
    assert real_dag.is_dag() is True


def test_cycle_detection_on_artificial_cyclic_graph():
    """Verify cycle detector detects artificial circular dependencies."""
    cyclic_catalog = CertificationCatalog()
    # Create 3 certs with a cycle: A -> B -> C -> A
    cert_a = Certification(
        id="cert-a", title="Cert A", provider="Org", level="Entry", category="General",
        description="", skills_gained=[], prerequisites=["cert-c"], next_steps=["cert-b"],
        link="", color="", resources=[], interests=[], estimated_hours=40, cost_usd=100.0,
    )
    cert_b = Certification(
        id="cert-b", title="Cert B", provider="Org", level="Intermediate", category="General",
        description="", skills_gained=[], prerequisites=["cert-a"], next_steps=["cert-c"],
        link="", color="", resources=[], interests=[], estimated_hours=40, cost_usd=100.0,
    )
    cert_c = Certification(
        id="cert-c", title="Cert C", provider="Org", level="Advanced", category="General",
        description="", skills_gained=[], prerequisites=["cert-b"], next_steps=["cert-a"],
        link="", color="", resources=[], interests=[], estimated_hours=40, cost_usd=100.0,
    )

    cyclic_dag = DAGEngine(cyclic_catalog)
    cyclic_dag.build_graph([cert_a, cert_b, cert_c])

    assert cyclic_dag.is_dag() is False
    cycles = cyclic_dag.detect_cycles()
    assert len(cycles) > 0


def test_resolve_prerequisites_topological_order(sample_dag: DAGEngine):
    """Verify resolving recursive prerequisites returns correct topological order."""
    # Root cert has no prereqs
    root_prereqs = sample_dag.resolve_prerequisites("cert-entry-1")
    assert len(root_prereqs) == 0

    # Intermediate cert
    inter1_prereqs = sample_dag.resolve_prerequisites("cert-inter-1")
    assert [c.id for c in inter1_prereqs] == ["cert-entry-1"]

    # Advanced cert requiring both branches
    adv_prereqs = sample_dag.resolve_prerequisites("cert-adv-1")
    adv_ids = [c.id for c in adv_prereqs]
    assert "cert-entry-1" in adv_ids
    assert "cert-entry-2" in adv_ids
    assert "cert-inter-1" in adv_ids
    assert "cert-inter-2" in adv_ids

    # Topological invariant: entry must precede inter
    assert adv_ids.index("cert-entry-1") < adv_ids.index("cert-inter-1")
    assert adv_ids.index("cert-entry-2") < adv_ids.index("cert-inter-2")


def test_resolve_dependents(sample_dag: DAGEngine):
    """Verify resolve_dependents returns unlocked descendants."""
    # Root cert unlocks intermediate and advanced certs
    unlocked = sample_dag.resolve_dependents("cert-entry-1")
    unlocked_ids = [c.id for c in unlocked]
    assert "cert-inter-1" in unlocked_ids
    assert "cert-inter-2" in unlocked_ids
    assert "cert-adv-1" in unlocked_ids

    # Leaf cert unlocks nothing
    leaf_unlocked = sample_dag.resolve_dependents("cert-adv-1")
    assert len(leaf_unlocked) == 0


def test_topological_sort_invariant(real_dag: DAGEngine, real_catalog: CertificationCatalog):
    """Verify full topological sort respects all prerequisite dependencies."""
    topo_order = real_dag.get_topological_sort()
    assert len(topo_order) == len(real_catalog)

    id_to_index = {c.id: idx for idx, c in enumerate(topo_order)}
    for cert in topo_order:
        for p in cert.prerequisites:
            if p in id_to_index:
                assert id_to_index[p] < id_to_index[cert.id], (
                    f"Topological violation: Prerequisite {p} (idx {id_to_index[p]}) "
                    f"appears after {cert.id} (idx {id_to_index[cert.id]})"
                )


def test_find_shortest_path(sample_dag: DAGEngine):
    """Verify BFS shortest progression path between certifications."""
    path = sample_dag.find_shortest_path("cert-entry-1", "cert-adv-1")
    assert path is not None
    path_ids = [c.id for c in path]
    assert path_ids[0] == "cert-entry-1"
    assert path_ids[-1] == "cert-adv-1"
    assert len(path_ids) == 3  # entry -> inter -> adv

    # Nonexistent disconnected path
    no_path = sample_dag.find_shortest_path("cert-adv-1", "cert-entry-1")
    assert no_path is None


def test_critical_path_and_difficulty_score(sample_dag: DAGEngine):
    """Verify critical path and difficulty calculation."""
    crit_path = sample_dag.calculate_critical_path("cert-adv-1")
    assert len(crit_path) > 0
    assert crit_path[-1].id == "cert-adv-1"

    score_entry = sample_dag.difficulty_score("cert-entry-1")
    score_adv = sample_dag.difficulty_score("cert-adv-1")
    assert score_adv > score_entry


def test_roots_and_leaves(sample_dag: DAGEngine):
    """Verify root nodes (entry points) and leaf nodes (capstones)."""
    roots = sample_dag.get_roots()
    root_ids = {r.id for r in roots}
    assert "cert-entry-1" in root_ids
    assert "cert-entry-2" in root_ids
    assert "cert-adv-1" not in root_ids

    leaves = sample_dag.get_leaves()
    leaf_ids = {l.id for l in leaves}
    assert "cert-adv-1" in leaf_ids
    assert "cert-entry-1" not in leaf_ids
