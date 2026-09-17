"""Directed Acyclic Graph (DAG) solver and progression engine for certifications.

Provides dependency resolution, topological sorting, shortest and critical path analysis,
cycle detection, and multi-factor certification difficulty scoring.
Zero third-party dependencies (100% Python Standard Library).
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from .catalog import Certification, CertificationCatalog


class DAGEngine:
    """Graph engine for analyzing certification prerequisites, progressions, and learning paths."""

    def __init__(self, catalog: Optional[CertificationCatalog] = None) -> None:
        """Initialize DAG engine with a CertificationCatalog."""
        self.catalog: CertificationCatalog = catalog if catalog is not None else CertificationCatalog()
        # forward_adj: cert_id -> set of cert_ids that unlock/follow this cert (nextSteps)
        self._forward_adj: Dict[str, Set[str]] = {}
        # reverse_adj: cert_id -> set of prerequisite cert_ids required before this cert
        self._reverse_adj: Dict[str, Set[str]] = {}
        self.build_graph()

    def build_graph(self, certs: Optional[Sequence[Certification]] = None) -> None:
        """Rebuild adjacency structures from catalog or provided certifications."""
        self._forward_adj.clear()
        self._reverse_adj.clear()

        cert_list = certs if certs is not None else self.catalog.get_all()

        # Initialize all nodes
        for cert in cert_list:
            if cert.id not in self._forward_adj:
                self._forward_adj[cert.id] = set()
            if cert.id not in self._reverse_adj:
                self._reverse_adj[cert.id] = set()

        # Populate edges and enforce bidirectional consistency
        for cert in cert_list:
            cid = cert.id
            # Prerequisites: p is a prerequisite for cid (p -> cid)
            for prereq_id in cert.prerequisites:
                prereq_id = str(prereq_id).strip()
                if prereq_id:
                    self._reverse_adj[cid].add(prereq_id)
                    if prereq_id not in self._forward_adj:
                        self._forward_adj[prereq_id] = set()
                    self._forward_adj[prereq_id].add(cid)

            # Next steps: cid unlocks next_id (cid -> next_id)
            for next_id in cert.next_steps:
                next_id = str(next_id).strip()
                if next_id:
                    self._forward_adj[cid].add(next_id)
                    if next_id not in self._reverse_adj:
                        self._reverse_adj[next_id] = set()
                    self._reverse_adj[next_id].add(cid)

    def detect_cycles(self) -> List[List[str]]:
        """Detect cycles in the certification dependency graph.

        Returns a list of detected cycles (each cycle is a list of node IDs).
        An empty list indicates that the graph is a strict DAG.
        """
        # State: 0 = unvisited, 1 = visiting (in stack), 2 = visited
        visited: Dict[str, int] = {}
        cycles: List[List[str]] = []
        stack: List[str] = []

        def dfs(node: str) -> None:
            visited[node] = 1
            stack.append(node)

            for neighbor in sorted(self._forward_adj.get(node, set())):
                neighbor_state = visited.get(neighbor, 0)
                if neighbor_state == 1:
                    # Found a back-edge indicating a cycle
                    try:
                        idx = stack.index(neighbor)
                        cycle_path = stack[idx:] + [neighbor]
                        cycles.append(cycle_path)
                    except ValueError:
                        cycles.append([node, neighbor])
                elif neighbor_state == 0:
                    dfs(neighbor)

            stack.pop()
            visited[node] = 2

        all_nodes = sorted(self._forward_adj.keys())
        for node in all_nodes:
            if visited.get(node, 0) == 0:
                dfs(node)

        return cycles

    def is_dag(self) -> bool:
        """Return True if the prerequisite graph is strictly acyclic."""
        return len(self.detect_cycles()) == 0

    def resolve_prerequisites(
        self,
        target_id: str,
        include_target: bool = False,
    ) -> List[Certification]:
        """Return complete recursive prerequisite list in topological order (earliest prerequisites first)."""
        target_id = str(target_id).strip()
        target_cert = self.catalog.get_by_id(target_id)
        if not target_cert:
            return []

        # Find all ancestor prerequisite nodes via BFS/DFS on reverse_adj
        ancestor_ids: Set[str] = set()
        queue: deque[str] = deque([target_id])

        while queue:
            curr = queue.popleft()
            for prereq_id in self._reverse_adj.get(curr, set()):
                if prereq_id not in ancestor_ids and prereq_id != target_id:
                    ancestor_ids.add(prereq_id)
                    queue.append(prereq_id)

        if not ancestor_ids:
            return [target_cert] if include_target else []

        # Topologically sort the ancestor subgraph
        nodes_to_sort = set(ancestor_ids)
        if include_target:
            nodes_to_sort.add(target_id)

        sorted_certs = self._topological_sort_subset(nodes_to_sort)
        return sorted_certs

    def resolve_dependents(
        self,
        cert_id: str,
        include_self: bool = False,
    ) -> List[Certification]:
        """Return all certifications unlocked directly or transitively by acquiring this cert."""
        cert_id = str(cert_id).strip()
        base_cert = self.catalog.get_by_id(cert_id)
        if not base_cert:
            return []

        descendant_ids: Set[str] = set()
        queue: deque[str] = deque([cert_id])

        while queue:
            curr = queue.popleft()
            for next_id in self._forward_adj.get(curr, set()):
                if next_id not in descendant_ids and next_id != cert_id:
                    descendant_ids.add(next_id)
                    queue.append(next_id)

        if not descendant_ids:
            return [base_cert] if include_self else []

        nodes_to_sort = set(descendant_ids)
        if include_self:
            nodes_to_sort.add(cert_id)

        return self._topological_sort_subset(nodes_to_sort)

    def _topological_sort_subset(self, subset_ids: Set[str]) -> List[Certification]:
        """Topologically sort a specific subset of certification IDs using Kahn's algorithm."""
        in_degree: Dict[str, int] = {cid: 0 for cid in subset_ids}

        for cid in subset_ids:
            for prereq in self._reverse_adj.get(cid, set()):
                if prereq in subset_ids:
                    in_degree[cid] += 1

        # Priority / order: Entry first, then Intermediate, then Advanced, then title
        def sort_key(cid: str) -> Tuple[int, str]:
            cert = self.catalog.get_by_id(cid)
            if not cert:
                return (99, cid)
            level_map = {
                "entry": 0,
                "foundational": 0,
                "intermediate": 1,
                "associate": 1,
                "advanced": 2,
                "expert": 2,
            }
            lvl_rank = level_map.get(cert.level.lower(), 5)
            return (lvl_rank, cert.title)

        ready_queue: List[str] = [cid for cid, deg in in_degree.items() if deg == 0]
        ready_queue.sort(key=sort_key)

        result_ids: List[str] = []

        while ready_queue:
            curr = ready_queue.pop(0)
            result_ids.append(curr)

            # Check neighbors
            for neighbor in self._forward_adj.get(curr, set()):
                if neighbor in subset_ids:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        ready_queue.append(neighbor)
                        ready_queue.sort(key=sort_key)

        # Fallback in case of orphan or detached items
        for cid in subset_ids:
            if cid not in result_ids:
                result_ids.append(cid)

        # Convert IDs to Certification instances
        resolved: List[Certification] = []
        for cid in result_ids:
            c = self.catalog.get_by_id(cid)
            if c:
                resolved.append(c)

        return resolved

    def get_topological_sort(self, category: Optional[str] = None) -> List[Certification]:
        """Return a valid topological sequence of all certs (or filtered by category)."""
        if category:
            cat_filter = category.lower().strip()
            certs = [c for c in self.catalog.get_all() if c.category.lower() == cat_filter]
            subset_ids = {c.id for c in certs}
            return self._topological_sort_subset(subset_ids)

        all_ids = {c.id for c in self.catalog.get_all()}
        return self._topological_sort_subset(all_ids)

    def find_shortest_path(
        self,
        start_id: str,
        target_id: str,
    ) -> Optional[List[Certification]]:
        """Find the shortest prerequisite/progression path between two certifications using BFS."""
        start_id = str(start_id).strip()
        target_id = str(target_id).strip()

        if start_id == target_id:
            cert = self.catalog.get_by_id(start_id)
            return [cert] if cert else None

        if start_id not in self._forward_adj or target_id not in self._reverse_adj:
            return None

        # BFS queue storing (current_node, path_of_ids)
        queue: deque[Tuple[str, List[str]]] = deque([(start_id, [start_id])])
        visited: Set[str] = {start_id}

        while queue:
            curr, path = queue.popleft()
            for neighbor in sorted(self._forward_adj.get(curr, set())):
                if neighbor == target_id:
                    full_path_ids = path + [neighbor]
                    path_certs = [self.catalog.get_by_id(cid) for cid in full_path_ids]
                    return [c for c in path_certs if c is not None]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return None

    def find_all_paths(
        self,
        start_id: str,
        target_id: str,
        max_depth: int = 15,
    ) -> List[List[Certification]]:
        """Find all distinct forward progression paths from start_id to target_id."""
        start_id = str(start_id).strip()
        target_id = str(target_id).strip()
        all_paths: List[List[Certification]] = []

        def dfs(curr: str, current_path: List[str]) -> None:
            if len(current_path) > max_depth:
                return
            if curr == target_id:
                certs = [self.catalog.get_by_id(cid) for cid in current_path]
                valid_certs = [c for c in certs if c is not None]
                all_paths.append(valid_certs)
                return

            for neighbor in sorted(self._forward_adj.get(curr, set())):
                if neighbor not in current_path:  # Prevent cycles
                    dfs(neighbor, current_path + [neighbor])

        dfs(start_id, [start_id])
        return all_paths

    def get_depth(self, cert_id: str) -> int:
        """Calculate the maximum prerequisite depth (longest chain from root) for a cert."""
        cert_id = str(cert_id).strip()
        prereqs = self._reverse_adj.get(cert_id, set())
        if not prereqs:
            return 0

        memo: Dict[str, int] = {}

        def compute_depth(cid: str) -> int:
            if cid in memo:
                return memo[cid]
            parents = self._reverse_adj.get(cid, set())
            if not parents:
                memo[cid] = 0
                return 0
            max_p = max(compute_depth(p) for p in parents) + 1
            memo[cid] = max_p
            return max_p

        return compute_depth(cert_id)

    def calculate_critical_path(
        self,
        target_id: str,
        metric: str = "hours",
    ) -> List[Certification]:
        """Find the critical path (heaviest prerequisite chain) leading to target_id.

        Args:
            target_id: ID of the target certification.
            metric: Weight metric - 'hours' (accumulated study hours),
                    'depth' (hop count), or 'difficulty'.
        """
        target_id = str(target_id).strip()
        target_cert = self.catalog.get_by_id(target_id)
        if not target_cert:
            return []

        # Get all ancestors including target
        prereqs = self.resolve_prerequisites(target_id, include_target=True)
        if not prereqs:
            return [target_cert]

        ancestor_ids = {c.id for c in prereqs}

        # Weight function
        def get_weight(cid: str) -> float:
            c = self.catalog.get_by_id(cid)
            if not c:
                return 1.0
            if metric == "hours":
                return float(c.estimated_hours)
            elif metric == "difficulty":
                return self.difficulty_score(cid)
            else:  # depth
                return 1.0

        # Topological order over ancestor subgraph
        topo_certs = self._topological_sort_subset(ancestor_ids)
        dist: Dict[str, float] = {}
        parent: Dict[str, Optional[str]] = {}

        for cert in topo_certs:
            cid = cert.id
            cid_weight = get_weight(cid)
            # Check all prerequisites of cid that are in ancestor_ids
            parents = [p for p in self._reverse_adj.get(cid, set()) if p in ancestor_ids]

            if not parents:
                dist[cid] = cid_weight
                parent[cid] = None
            else:
                best_parent = None
                max_d = -1.0
                for p in parents:
                    p_dist = dist.get(p, 0.0)
                    if p_dist > max_d:
                        max_d = p_dist
                        best_parent = p
                dist[cid] = max_d + cid_weight
                parent[cid] = best_parent

        # Reconstruct path from target backwards
        path_ids: List[str] = []
        curr: Optional[str] = target_id
        while curr is not None:
            path_ids.append(curr)
            curr = parent.get(curr)

        path_ids.reverse()

        result: List[Certification] = []
        for cid in path_ids:
            c = self.catalog.get_by_id(cid)
            if c:
                result.append(c)

        return result

    def difficulty_score(self, cert_id: str) -> float:
        """Compute holistic difficulty score (1.0 to 15.0+) based on level, depth, prerequisites, skills, and hours."""
        cert_id = str(cert_id).strip()
        cert = self.catalog.get_by_id(cert_id)
        if not cert:
            return 1.0

        # Base level score
        lvl = cert.level.lower()
        if "entry" in lvl or "foundational" in lvl:
            base = 1.0
        elif "intermediate" in lvl or "associate" in lvl:
            base = 3.0
        elif "advanced" in lvl or "expert" or "specialty" in lvl or "professional" in lvl:
            base = 6.0
        else:
            base = 2.5

        # Prerequisite depth & count
        depth = self.get_depth(cert_id)
        prereqs_count = len(self.resolve_prerequisites(cert_id, include_target=False))

        # Skills complexity
        skills_count = len(cert.skills_gained)

        # Hours weight
        hours_factor = (cert.estimated_hours / 40.0) * 0.6

        score = base + (depth * 1.2) + (prereqs_count * 0.4) + (skills_count * 0.15) + hours_factor
        return round(score, 2)

    def get_roots(self, category: Optional[str] = None) -> List[Certification]:
        """Return root certifications (certifications with no prerequisites)."""
        roots: List[Certification] = []
        for cert in self.catalog.get_all():
            if category and cert.category.lower() != category.lower().strip():
                continue
            prereqs = self._reverse_adj.get(cert.id, set())
            if not prereqs:
                roots.append(cert)
        return roots

    def get_leaves(self, category: Optional[str] = None) -> List[Certification]:
        """Return leaf certifications (capstone/terminal certifications with no further next steps)."""
        leaves: List[Certification] = []
        for cert in self.catalog.get_all():
            if category and cert.category.lower() != category.lower().strip():
                continue
            next_steps = self._forward_adj.get(cert.id, set())
            if not next_steps:
                leaves.append(cert)
        return leaves
