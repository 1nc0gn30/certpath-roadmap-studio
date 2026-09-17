"""CertPath Roadmap Studio - Intelligent Certification DAG & Career Pathing System.

A zero-dependency Python package and Model Context Protocol (MCP) server for
resolving IT, Cloud, and Developer certification prerequisites, calculating
topological study orders, and generating personalized career roadmaps.

Zero third-party runtime dependencies (100% Python Standard Library).
"""

from __future__ import annotations

__version__ = "0.1.0"
__title__ = "certpath-roadmap-studio"
__description__ = "Intelligent Certification DAG & Career Pathing System with MCP Server & CLI"
__author__ = "CertPath Roadmap Studio Team"
__license__ = "MIT"

# Core Models & Catalog
from .catalog import (
    Certification,
    CertificationCatalog,
    CertificationResource,
)

# Graph & DAG Engine
from .dag_engine import DAGEngine

# Career Roadmap Planner
from .roadmap_planner import (
    BUILTIN_ROLES,
    CareerRole,
    RoadmapMilestone,
    RoadmapPhase,
    RoadmapPlan,
    RoadmapPlanner,
    SkillGapResult,
)

# Visual & Data Exporters
from .matrix_exporter import (
    export_ascii_tree,
    export_json_ld,
    export_markdown,
    export_mermaid,
)

# Protocol & CLI (conditional for concurrent subagent initialization)
try:
    from .mcp_server import MCPServer
except ImportError:
    MCPServer = None  # type: ignore


def cli_main(argv=None):
    """Entry point for the certpath CLI."""
    from .cli import main
    return main(argv)

__all__ = [
    "__version__",
    "__title__",
    "__description__",
    "__author__",
    "__license__",
    # Core Entities
    "Certification",
    "CertificationResource",
    "CertificationCatalog",
    # Graph Engine
    "DAGEngine",
    # Planner & Roles
    "RoadmapPlanner",
    "RoadmapPlan",
    "RoadmapPhase",
    "RoadmapMilestone",
    "CareerRole",
    "BUILTIN_ROLES",
    "SkillGapResult",
    # Exporters
    "export_mermaid",
    "export_markdown",
    "export_ascii_tree",
    "export_json_ld",
    # Server & CLI
    "MCPServer",
    "cli_main",
]
