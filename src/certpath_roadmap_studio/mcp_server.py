"""Model Context Protocol (MCP) Server for CertPath Roadmap Studio.

Implements JSON-RPC 2.0 over stdio transport according to the MCP specification.
Exposes tools for searching certifications, resolving prerequisite DAG chains,
generating personalized career roadmaps, comparing credentials, and exporting visual diagrams.

Zero third-party runtime dependencies (100% Python Standard Library).
"""

from __future__ import annotations

import json
import os
import platform
import signal
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from .catalog import Certification, CertificationCatalog
from .compat import get_platform_name
from .dag_engine import DAGEngine
from .matrix_exporter import (
    export_ascii_tree,
    export_json_ld,
    export_markdown,
    export_mermaid,
)
from .roadmap_planner import BUILTIN_ROLES, CareerRole, RoadmapPlan, RoadmapPlanner

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "certpath-roadmap-studio"
SERVER_VERSION = "0.1.0"


def _log_stderr(message: str) -> None:
    """Log diagnostic information to stderr to avoid corrupting stdio JSON-RPC stream."""
    sys.stderr.write(f"[{SERVER_NAME}] {message}\n")
    sys.stderr.flush()


class MCPServer:
    """Model Context Protocol (MCP) server managing JSON-RPC 2.0 interactions over stdio."""

    def __init__(
        self,
        catalog: Optional[CertificationCatalog] = None,
        dag_engine: Optional[DAGEngine] = None,
        planner: Optional[RoadmapPlanner] = None,
    ) -> None:
        """Initialize MCP Server with catalog, DAG engine, and roadmap planner."""
        self.catalog: CertificationCatalog = (
            catalog if catalog is not None else CertificationCatalog()
        )
        self.dag_engine: DAGEngine = (
            dag_engine if dag_engine is not None else DAGEngine(self.catalog)
        )
        self.planner: RoadmapPlanner = (
            planner if planner is not None else RoadmapPlanner(self.catalog, self.dag_engine)
        )
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._running = False
        self._register_default_tools()

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable[[Dict[str, Any]], Any],
    ) -> None:
        """Register an MCP tool definition and its invocation handler."""
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
        }
        self._handlers[name] = handler

    def _register_default_tools(self) -> None:
        """Register all built-in certification roadmap MCP tools."""
        # 1. certpath_search
        self.register_tool(
            name="certpath_search",
            description=(
                "Search and filter the IT/Cloud/Developer certification catalog by keyword, "
                "provider, level, category, skill, or interest."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free text query matching title, exam code, description, or skills.",
                    },
                    "provider": {
                        "type": "string",
                        "description": "Filter by certification provider (e.g. 'AWS', 'CompTIA', 'Microsoft', 'Google', 'freeCodeCamp').",
                    },
                    "level": {
                        "type": "string",
                        "enum": ["Entry", "Intermediate", "Advanced"],
                        "description": "Filter by difficulty tier.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category domain (e.g. 'Cloud Computing', 'Cyber Security', 'AI Development', 'Web Development').",
                    },
                    "skill": {
                        "type": "string",
                        "description": "Filter by a specific skill gained (e.g. 'Kubernetes', 'React', 'IAM', 'PyTorch').",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Maximum number of results to return (default: 20).",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                        "description": "Output formatting representation.",
                    },
                },
            },
            handler=self._tool_search,
        )

        # 2. certpath_resolve_prereqs
        self.register_tool(
            name="certpath_resolve_prereqs",
            description=(
                "Calculate the complete prerequisite dependency chain and optimal topological study order "
                "required to achieve a target certification."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "cert_id": {
                        "type": "string",
                        "description": "The unique target certification ID (e.g., 'cloud-aws-pro', 'cyber-cissp', 'web-fullstack-open').",
                    },
                    "include_target": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether to include the target certification at the end of the prerequisite chain.",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                        "description": "Output formatting representation.",
                    },
                },
                "required": ["cert_id"],
            },
            handler=self._tool_resolve_prereqs,
        )

        # 3. certpath_plan_career
        self.register_tool(
            name="certpath_plan_career",
            description=(
                "Generate a customized, multi-phase career roadmap with milestone timelines, study pace, "
                "and budget calculations from current skills to target role or certification."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "Career role archetype ID (e.g. 'cloud_security_architect', 'ai_ml_engineer', 'fullstack_devops_lead', 'soc_analyst', 'penetration_tester', 'data_platform_architect').",
                    },
                    "target": {
                        "type": "string",
                        "description": "Target certification ID if planning for a specific flagship credential instead of a role.",
                    },
                    "current": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of certification IDs already completed by the user.",
                    },
                    "hours_per_week": {
                        "type": "integer",
                        "default": 10,
                        "description": "Weekly study time allocation in hours (default: 10).",
                    },
                    "max_budget": {
                        "type": "number",
                        "description": "Optional maximum exam budget limit in USD.",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json", "mermaid"],
                        "default": "markdown",
                        "description": "Output formatting representation.",
                    },
                },
            },
            handler=self._tool_plan_career,
        )

        # 4. certpath_compare
        self.register_tool(
            name="certpath_compare",
            description=(
                "Compare 2 or more certifications side-by-side on difficulty, domains, skills gained, "
                "exam fees, study hours, and prerequisite complexity."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "cert_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "description": "List of 2 or more certification IDs to compare (e.g. ['cloud-aws-saa', 'cloud-azure-az104', 'cloud-gcp-ace']).",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                        "description": "Output formatting representation.",
                    },
                },
                "required": ["cert_ids"],
            },
            handler=self._tool_compare,
        )

        # 5. certpath_export_dag
        self.register_tool(
            name="certpath_export_dag",
            description=(
                "Export certification DAG or subgraphs to Mermaid flowchart syntax, ASCII hierarchy trees, "
                "or Schema.org JSON-LD."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "cert_id": {
                        "type": "string",
                        "description": "Target certification ID for focused tree or subgraph.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Category domain filter for category-level graph.",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["mermaid", "ascii_tree", "json", "json_ld"],
                        "description": "Visual or structural export format.",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["LR", "TD"],
                        "default": "LR",
                        "description": "Mermaid flowchart layout orientation (LR=left-to-right, TD=top-down).",
                    },
                },
                "required": ["format"],
            },
            handler=self._tool_export_dag,
        )

        # 6. certpath_roles
        self.register_tool(
            name="certpath_roles",
            description="List available built-in and registered career role archetypes with target credentials and required skills.",
            input_schema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Optional category domain filter.",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                        "description": "Output formatting representation.",
                    },
                },
            },
            handler=self._tool_roles,
        )

        # 7. certpath_catalog_stats
        self.register_tool(
            name="certpath_catalog_stats",
            description="Return summary statistics across providers, domains, levels, and graph connectivity.",
            input_schema={
                "type": "object",
                "properties": {
                    "verbose": {
                        "type": "boolean",
                        "default": False,
                        "description": "Whether to include detailed root/leaf nodes and graph metrics.",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                        "description": "Output formatting representation.",
                    },
                },
            },
            handler=self._tool_catalog_stats,
        )

        # 8. certpath_diagnostics
        self.register_tool(
            name="certpath_diagnostics",
            description="Run system health checks, verify DAG acyclicity, catalog integrity, and runtime environment.",
            input_schema={"type": "object", "properties": {}},
            handler=self._tool_diagnostics,
        )

        # 9. certpath_simulate_velocity
        self.register_tool(
            name="certpath_simulate_velocity",
            description=(
                "Simulate roadmap completion timeline with cognitive fatigue / burnout analysis, "
                "exam retake risk, and Monte Carlo stochastic probability distributions (P50, P80, P95)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Target career role ID or certification ID (e.g. 'cloud_security_architect' or 'cloud-aws-pro').",
                    },
                    "weekly_hours": {
                        "type": "number",
                        "default": 10.0,
                        "description": "Study hours available per week (e.g. 5, 10, 20).",
                    },
                    "experience_level": {
                        "type": "string",
                        "enum": ["beginner", "intermediate", "advanced", "expert"],
                        "default": "intermediate",
                        "description": "Baseline learner experience level affecting velocity multiplier and pass rate.",
                    },
                    "current_certs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Certifications already acquired to skip.",
                    },
                    "trials": {
                        "type": "integer",
                        "default": 500,
                        "description": "Number of stochastic Monte Carlo trials (50 to 5000).",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                        "description": "Output formatting representation.",
                    },
                },
                "required": ["target"],
            },
            handler=self._tool_simulate_velocity,
        )

        # 10. certpath_calculate_roi
        self.register_tool(
            name="certpath_calculate_roi",
            description=(
                "Calculate financial return on investment (ROI), salary premium, payback horizon (in months), "
                "hourly study value, and 5-year net earnings for any certification."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "cert_id": {
                        "type": "string",
                        "description": "Certification ID or exam code (e.g. 'cloud-aws-saa' or 'sec-comptia-secplus').",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                        "description": "Output formatting representation.",
                    },
                },
                "required": ["cert_id"],
            },
            handler=self._tool_calculate_roi,
        )

        # 11. certpath_skill_overlap
        self.register_tool(
            name="certpath_skill_overlap",
            description=(
                "Quantify knowledge and skill overlap between two certifications. Computes Jaccard competency overlap, "
                "shared concepts, and study-hours saved via synergistic learning."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "cert_a_id": {
                        "type": "string",
                        "description": "First certification ID (e.g. 'cloud-aws-saa').",
                    },
                    "cert_b_id": {
                        "type": "string",
                        "description": "Second certification ID (e.g. 'sec-aws-sec-spec' or 'devops-hashicorp-terraform').",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                        "description": "Output formatting representation.",
                    },
                },
                "required": ["cert_a_id", "cert_b_id"],
            },
            handler=self._tool_skill_overlap,
        )

        # 12. certpath_portfolio_valuation
        self.register_tool(
            name="certpath_portfolio_valuation",
            description=(
                "Evaluate comprehensive market value, vendor diversification score (HHI), multi-cloud quotient, "
                "security index, and expected salary range for a portfolio of credentials."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "cert_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of certification IDs in the portfolio.",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                        "description": "Output formatting representation.",
                    },
                },
                "required": ["cert_ids"],
            },
            handler=self._tool_portfolio_valuation,
        )

    # -------------------------------------------------------------------------
    # Tool Handler Implementations
    # -------------------------------------------------------------------------

    def _tool_search(self, args: Dict[str, Any]) -> str:
        """Handler for certpath_search."""
        query = args.get("query")
        provider = args.get("provider")
        level = args.get("level")
        category = args.get("category")
        skill = args.get("skill")
        limit = max(1, int(args.get("limit", 20)))
        output_format = str(args.get("format", "markdown")).lower()

        results = self.catalog.search(
            query=query,
            provider=provider,
            level=level,
            category=category,
            skill=skill,
        )
        sliced = results[:limit]

        if output_format == "json":
            return json.dumps(
                {
                    "total_matches": len(results),
                    "returned_count": len(sliced),
                    "results": [c.to_dict() for c in sliced],
                },
                indent=2,
            )

        # Markdown output
        lines: List[str] = [
            f"### 🔍 Certification Search Results ({len(sliced)} of {len(results)} matches)",
            "",
        ]
        if not sliced:
            lines.append("No certifications found matching the specified search criteria.")
            return "\n".join(lines)

        lines.append("| ID | Title | Provider | Level | Category | Hours | Exam Fee |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for cert in sliced:
            fee = f"${cert.cost_usd:.0f}" if cert.cost_usd > 0 else "Free"
            code_str = f" (`{cert.exam_code}`)" if cert.exam_code else ""
            t_link = f"[{cert.title}]({cert.link})" if cert.link else cert.title
            lines.append(
                f"| `{cert.id}` | **{t_link}**{code_str} | {cert.provider} | `{cert.level}` | {cert.category} | {cert.estimated_hours}h | {fee} |"
            )

        lines.append("")
        lines.append("#### Highlighted Skills & Prerequisites:")
        for cert in sliced[:5]:
            skills = ", ".join(f"`{s}`" for s in cert.skills_gained[:6]) or "None listed"
            prereqs = ", ".join(f"`{p}`" for p in cert.prerequisites) or "None (Root Entry)"
            lines.append(f"- **`{cert.id}`** ({cert.title}):")
            lines.append(f"  - **Skills:** {skills}")
            lines.append(f"  - **Prerequisites:** {prereqs}")

        return "\n".join(lines)

    def _tool_resolve_prereqs(self, args: Dict[str, Any]) -> str:
        """Handler for certpath_resolve_prereqs."""
        cert_id = str(args.get("cert_id", "")).strip()
        include_target = bool(args.get("include_target", True))
        output_format = str(args.get("format", "markdown")).lower()

        target_cert = self.catalog.get_by_id(cert_id)
        if not target_cert:
            return f"Error: Certification with ID '{cert_id}' was not found in catalog."

        chain = self.dag_engine.resolve_prerequisites(cert_id, include_target=include_target)
        depth = self.dag_engine.get_depth(cert_id)
        difficulty = self.dag_engine.difficulty_score(cert_id)
        dependents = self.dag_engine.resolve_dependents(cert_id, include_self=False)

        total_hours = sum(c.estimated_hours for c in chain)
        total_cost = sum(c.cost_usd for c in chain)

        if output_format == "json":
            return json.dumps(
                {
                    "target_cert": target_cert.to_dict(),
                    "prerequisite_depth": depth,
                    "difficulty_score": difficulty,
                    "total_chain_hours": total_hours,
                    "total_chain_cost_usd": total_cost,
                    "topological_sequence": [c.to_dict() for c in chain],
                    "unlocked_next_steps": [d.to_dict() for d in dependents],
                },
                indent=2,
            )

        # Markdown format
        lines: List[str] = [
            f"### 🪜 Prerequisite Sequence for **{target_cert.title}** (`{target_cert.id}`)",
            f"> **Provider:** {target_cert.provider} &nbsp;|&nbsp; **Level:** `{target_cert.level}` &nbsp;|&nbsp; **Difficulty Score:** `{difficulty}/15.0` &nbsp;|&nbsp; **Prereq Depth:** `{depth}` hops",
            "",
            f"**Total Learning Path Effort:** `{total_hours} hours` &nbsp;|&nbsp; **Total Exam Fees:** `${total_cost:,.2f} USD`",
            "",
            "#### 📋 Recommended Study Sequence (Topological Order):",
            "",
        ]

        if not chain or (len(chain) == 1 and chain[0].id == cert_id):
            lines.append("🎉 **No prerequisites required!** This is a foundational root certification.")
        else:
            for idx, cert in enumerate(chain, start=1):
                is_curr_target = cert.id == cert_id
                tag = " 🎯 *(Target Goal)*" if is_curr_target else ""
                cost_str = f"${cert.cost_usd:.0f}" if cert.cost_usd > 0 else "Free"
                code_str = f"`{cert.exam_code}` &bull; " if cert.exam_code else ""
                lines.append(
                    f"{idx}. **{cert.title}** (`{cert.id}`){tag}\n"
                    f"   - **Provider:** {cert.provider} &bull; **Level:** `{cert.level}` &bull; {code_str}{cert.estimated_hours}h &bull; {cost_str}\n"
                    f"   - **Key Skills:** {', '.join(cert.skills_gained[:5])}"
                )

        if dependents:
            lines.append("")
            lines.append(f"#### 🔓 Next Credentials Unlocked Upon Passing `{target_cert.id}`:")
            for dep in dependents[:6]:
                d_fee = f"${dep.cost_usd:.0f}" if dep.cost_usd > 0 else "Free"
                lines.append(f"- **{dep.title}** (`{dep.id}`) &mdash; *{dep.provider} &bull; `{dep.level}` &bull; {d_fee}*")

        return "\n".join(lines)

    def _tool_plan_career(self, args: Dict[str, Any]) -> str:
        """Handler for certpath_plan_career."""
        role_id = args.get("role")
        target_id = args.get("target")
        current_certs = args.get("current") or []
        hours_per_week = int(args.get("hours_per_week", 10))
        max_budget = args.get("max_budget")
        if max_budget is not None:
            max_budget = float(max_budget)
        output_format = str(args.get("format", "markdown")).lower()

        if isinstance(current_certs, str):
            current_certs = [c.strip() for c in current_certs.split(",") if c.strip()]

        target_identifier = role_id or target_id
        if not target_identifier:
            # Default to popular role
            target_identifier = "cloud_security_architect"

        try:
            plan = self.planner.generate_roadmap(
                target_role_or_cert=target_identifier,
                current_certs=current_certs,
                weekly_hours=hours_per_week,
                max_budget=max_budget,
            )
        except Exception as err:
            return f"Error generating roadmap plan: {err}"

        if output_format == "json":
            return json.dumps(plan.to_dict(), indent=2)
        elif output_format == "mermaid":
            return export_mermaid(plan, direction="LR", group_by="phase")

        # Markdown representation
        return export_markdown(plan, include_resources=True)

    def _tool_compare(self, args: Dict[str, Any]) -> str:
        """Handler for certpath_compare."""
        raw_ids = args.get("cert_ids", [])
        output_format = str(args.get("format", "markdown")).lower()

        if isinstance(raw_ids, str):
            raw_ids = [i.strip() for i in raw_ids.split(",") if i.strip()]

        cert_ids = [str(i).strip() for i in raw_ids if str(i).strip()]
        if len(cert_ids) < 2:
            return "Error: Please provide at least 2 certification IDs to compare."

        certs: List[Certification] = []
        missing: List[str] = []
        for cid in cert_ids:
            c = self.catalog.get_by_id(cid)
            if c:
                certs.append(c)
            else:
                missing.append(cid)

        if missing:
            return f"Error: The following certification IDs were not found: {', '.join(missing)}"

        if output_format == "json":
            comparison_data = []
            for cert in certs:
                comparison_data.append(
                    {
                        "cert": cert.to_dict(),
                        "difficulty_score": self.dag_engine.difficulty_score(cert.id),
                        "prerequisite_depth": self.dag_engine.get_depth(cert.id),
                        "total_prereqs_count": len(
                            self.dag_engine.resolve_prerequisites(cert.id, include_target=False)
                        ),
                    }
                )
            return json.dumps(comparison_data, indent=2)

        # Markdown Comparison
        lines: List[str] = [
            f"### ⚖️ Side-by-Side Certification Comparison ({len(certs)} Credentials)",
            "",
            "| Feature | " + " | ".join(f"**{c.title}**" for c in certs) + " |",
            "| :--- | " + " | ".join(":---" for _ in certs) + " |",
            "| **ID** | " + " | ".join(f"`{c.id}`" for c in certs) + " |",
            "| **Provider** | " + " | ".join(c.provider for c in certs) + " |",
            "| **Level** | " + " | ".join(f"`{c.level}`" for c in certs) + " |",
            "| **Category** | " + " | ".join(c.category for c in certs) + " |",
            "| **Exam Code** | " + " | ".join(f"`{c.exam_code or 'N/A'}`" for c in certs) + " |",
            "| **Study Hours** | " + " | ".join(f"{c.estimated_hours}h" for c in certs) + " |",
            "| **Exam Fee (USD)** | "
            + " | ".join(f"${c.cost_usd:.0f}" if c.cost_usd > 0 else "Free" for c in certs)
            + " |",
            "| **Difficulty Score** | "
            + " | ".join(f"{self.dag_engine.difficulty_score(c.id):.1f}/15" for c in certs)
            + " |",
            "| **Prereq Depth** | "
            + " | ".join(f"{self.dag_engine.get_depth(c.id)} hops" for c in certs)
            + " |",
            "| **Prerequisites** | "
            + " | ".join(
                ", ".join(f"`{p}`" for p in c.prerequisites) or "None (Root)" for c in certs
            )
            + " |",
            "",
            "#### 🎯 Skills Breakdown:",
        ]

        for cert in certs:
            lines.append(f"- **{cert.title}:** {', '.join(f'`{s}`' for s in cert.skills_gained)}")

        # Find overlapping skills
        all_skills_sets = [set(c.skills_gained) for c in certs]
        common_skills = set.intersection(*all_skills_sets) if all_skills_sets else set()
        if common_skills:
            lines.append("")
            lines.append(f"**🤝 Common Overlapping Competencies:** {', '.join(f'`{s}`' for s in sorted(common_skills))}")

        return "\n".join(lines)

    def _tool_export_dag(self, args: Dict[str, Any]) -> str:
        """Handler for certpath_export_dag."""
        cert_id = args.get("cert_id")
        category = args.get("category")
        export_fmt = str(args.get("format", "mermaid")).lower()
        direction = str(args.get("direction", "LR")).upper()

        if export_fmt == "ascii_tree":
            if not cert_id:
                # Default to an iconic anchor cert
                cert_id = "cloud-aws-pro" if "cloud-aws-pro" in self.catalog else (self.catalog.get_all()[0].id if self.catalog.get_all() else "")
            return export_ascii_tree(cert_id, self.catalog, self.dag_engine)

        elif export_fmt == "mermaid":
            if cert_id:
                chain = self.dag_engine.resolve_prerequisites(cert_id, include_target=True)
                return export_mermaid(chain, direction=direction, group_by="category")
            elif category:
                certs = [c for c in self.catalog.get_all() if c.category.lower() == category.lower().strip()]
                return export_mermaid(certs, direction=direction, group_by="none")
            else:
                return export_mermaid(self.catalog, direction=direction, group_by="category")

        elif export_fmt == "json_ld":
            if cert_id:
                c = self.catalog.get_by_id(cert_id)
                if c:
                    return export_json_ld(c)
                return f"Error: Cert '{cert_id}' not found."
            else:
                plan = self.planner.generate_roadmap("cloud_security_architect")
                return export_json_ld(plan)

        elif export_fmt == "json":
            if cert_id:
                c = self.catalog.get_by_id(cert_id)
                return json.dumps(c.to_dict() if c else {}, indent=2)
            else:
                return json.dumps([c.to_dict() for c in self.catalog.get_all()], indent=2)

        return f"Error: Unsupported export format '{export_fmt}'."

    def _tool_roles(self, args: Dict[str, Any]) -> str:
        """Handler for certpath_roles."""
        cat_filter = args.get("category")
        output_format = str(args.get("format", "markdown")).lower()

        roles = self.planner.get_roles()
        if cat_filter:
            roles = [r for r in roles if r.category.lower() == cat_filter.lower().strip()]

        if output_format == "json":
            return json.dumps([r.to_dict() for r in roles], indent=2)

        lines: List[str] = [
            f"### 💼 Available Career Role Templates ({len(roles)} Archetypes)",
            "",
            "| Role ID | Title | Category | Target Certifications | Target Level |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for r in roles:
            targets = ", ".join(f"`{t}`" for t in r.target_certs)
            lines.append(f"| `{r.role_id}` | **{r.title}** | {r.category} | {targets} | `{r.target_level}` |")

        lines.append("")
        lines.append("#### Role Descriptions & Skills:")
        for r in roles:
            skills = ", ".join(f"`{s}`" for s in r.key_skills)
            lines.append(f"- **{r.title}** (`{r.role_id}`):")
            lines.append(f"  - *{r.description}*")
            lines.append(f"  - **Key Skills:** {skills}")

        return "\n".join(lines)

    def _tool_catalog_stats(self, args: Dict[str, Any]) -> str:
        """Handler for certpath_catalog_stats."""
        verbose = bool(args.get("verbose", False))
        output_format = str(args.get("format", "markdown")).lower()

        stats = self.catalog.summary_statistics()
        is_acyclic = self.dag_engine.is_dag()
        cycles = self.dag_engine.detect_cycles()
        roots = self.dag_engine.get_roots()
        leaves = self.dag_engine.get_leaves()

        data: Dict[str, Any] = {
            **stats,
            "is_strict_dag": is_acyclic,
            "cycles_detected": len(cycles),
            "root_certifications_count": len(roots),
            "leaf_certifications_count": len(leaves),
        }

        if output_format == "json":
            if verbose:
                data["root_cert_ids"] = [r.id for r in roots]
                data["leaf_cert_ids"] = [l.id for l in leaves]
            return json.dumps(data, indent=2)

        lines: List[str] = [
            "### 📊 Certification Catalog & DAG Telemetry",
            "",
            f"- **Total Certifications:** `{stats['total_certs']:,}` credentials",
            f"- **Total Skills Indexed:** `{stats['total_skills']:,}` unique competencies",
            f"- **Average Study Effort:** `{stats['average_hours']} hours` per credential",
            f"- **Average Exam Fee:** `${stats['average_cost']:.2f} USD`",
            f"- **Free / Open Credentials:** `{stats['free_certs_count']}` credentials",
            f"- **Prerequisite DAG Integrity:** `{'Strictly Acyclic (Valid DAG)' if is_acyclic else 'Contains Cycles'}`",
            f"- **Root Entry Points (No Prerequisites):** `{len(roots)}` certs",
            f"- **Capstone Landmark Credentials:** `{len(leaves)}` certs",
            "",
            "#### 📁 Breakdown by Category:",
        ]
        for cat, cnt in stats["by_category"].items():
            lines.append(f"- **{cat}:** {cnt} certs")

        lines.append("")
        lines.append("#### 🏢 Top Certification Providers:")
        top_providers = list(stats["by_provider"].items())[:8]
        for prov, cnt in top_providers:
            lines.append(f"- **{prov}:** {cnt} certs")

        return "\n".join(lines)

    def _tool_diagnostics(self, args: Dict[str, Any]) -> str:
        """Handler for certpath_diagnostics."""
        is_acyclic = self.dag_engine.is_dag()
        cycles = self.dag_engine.detect_cycles()
        roots = self.dag_engine.get_roots()
        leaves = self.dag_engine.get_leaves()

        diag = {
            "status": "healthy",
            "server": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
                "protocol_version": PROTOCOL_VERSION,
            },
            "environment": {
                "platform": get_platform_name(),
                "os": platform.system(),
                "os_release": platform.release(),
                "python_version": sys.version.split()[0],
                "executable": sys.executable,
                "cwd": os.getcwd(),
            },
            "catalog": {
                "loaded_certifications": len(self.catalog),
                "categories_count": len(self.catalog.get_categories()),
                "providers_count": len(self.catalog.get_providers()),
                "total_unique_skills": len(self.catalog.get_all_skills()),
            },
            "dag_engine": {
                "is_dag": is_acyclic,
                "cycles_count": len(cycles),
                "root_nodes_count": len(roots),
                "leaf_nodes_count": len(leaves),
            },
            "planner": {
                "registered_roles_count": len(self.planner.get_roles()),
            },
            "mcp_tools_count": len(self._tools),
        }

        return json.dumps(diag, indent=2)

    def _tool_simulate_velocity(self, args: Dict[str, Any]) -> str:
        """Handler for certpath_simulate_velocity."""
        from .velocity_simulator import simulate_velocity

        target = args.get("target")
        if not target:
            return "Error: Parameter 'target' (role ID or certification ID) is required."

        weekly_hours = float(args.get("weekly_hours", 10.0))
        experience_level = str(args.get("experience_level", "intermediate"))
        current_certs = args.get("current_certs") or []
        trials = int(args.get("trials", 500))
        output_format = str(args.get("format", "markdown")).lower()

        try:
            plan = self.planner.generate_roadmap(
                target_role_or_cert=target,
                current_certs=current_certs,
                weekly_hours=int(weekly_hours),
            )
            report = simulate_velocity(
                plan_or_certs=plan,
                weekly_hours=weekly_hours,
                experience_level=experience_level,
                simulation_trials=trials,
            )
        except Exception as e:
            return f"Error simulating learning velocity for target '{target}': {e}"

        if output_format == "json":
            return json.dumps(report.to_dict(), indent=2)

        mc = report.monte_carlo
        lines: List[str] = [
            f"### 🚀 Learning Velocity & Monte Carlo Schedule Simulation: {report.target_name}",
            "",
            f"- **Learner Experience Tier:** `{report.experience_level.title()}` (speed multiplier: `{report.learning_speed_multiplier:.2f}x`)",
            f"- **Weekly Study Commitment:** `{report.weekly_hours:.0f} hours/week`",
            f"- **Effort Projection:** `{report.total_nominal_hours} nominal hours` -> `{report.total_adjusted_hours:.1f} adjusted hours`",
            f"- **Cognitive Fatigue Index:** `{report.fatigue_index:.1f}/100`",
            f"- **Pacing Advisory:** *{report.pacing_recommendation}*",
            "",
            "#### 🎲 Monte Carlo Probabilistic Completion Milestones (500 Stochastic Trials):",
            f"- **P50 (Median):** `{mc.weeks_p50:.1f} weeks` (~{mc.weeks_p50 / 4.33:.1f} months) — Expected Date: **{mc.completion_date_p50}** | Cost: **${mc.cost_p50:.2f}**",
            f"- **P80 (Realistic):** `{mc.weeks_p80:.1f} weeks` (~{mc.weeks_p80 / 4.33:.1f} months) — Expected Date: **{mc.completion_date_p80}** | Cost: **${mc.cost_p80:.2f}**",
            f"- **P95 (Conservative):** `{mc.weeks_p95:.1f} weeks` (~{mc.weeks_p95 / 4.33:.1f} months) — Expected Date: **{mc.completion_date_p95}** | Cost: **${mc.cost_p95:.2f}**",
            f"- **Retake Probability:** P50: `{mc.retakes_p50:.1f}` retakes | P95: `{mc.retakes_p95:.1f}` retakes",
            "",
        ]

        if report.fatigue_warnings:
            lines.append("#### ⚠️ Cognitive Fatigue & Burnout Risk Alerts:")
            for w in report.fatigue_warnings:
                lines.append(f"- **[{w.risk_level}] {w.title}** (Burnout Score: `{w.burnout_score:.2f}`): {w.recommendation}")
            lines.append("")

        lines.append("#### 📅 Milestone Study Sequence:")
        lines.append("| # | Certification | Level | Hours | Est. Weeks | Completion Date | Pass Prob |")
        lines.append("| -: | :--- | :--- | -: | -: | :--- | -: |")
        for m in report.milestones:
            lines.append(
                f"| {m.index} | **{m.title}** | `{m.level}` | {m.adjusted_hours:.0f}h | {m.estimated_weeks:.1f}w | {m.completion_date_iso} | {m.pass_probability * 100:.0f}% |"
            )

        lines.append("")
        lines.append("```text")
        lines.append(report.ascii_burndown_chart)
        lines.append("```")

        return "\n".join(lines)

    def _tool_calculate_roi(self, args: Dict[str, Any]) -> str:
        """Handler for certpath_calculate_roi."""
        from .roi_calculator import calculate_cert_roi, format_roi_scorecard

        cert_id = args.get("cert_id", "").strip()
        if not cert_id:
            return "Error: Parameter 'cert_id' is required."

        cert = self.catalog.get(cert_id)
        if not cert:
            # Fallback search by title or exam code
            matches = self.catalog.search(query=cert_id)
            if matches:
                cert = matches[0]

        if not cert:
            return f"Error: Certification '{cert_id}' not found in catalog."

        analysis = calculate_cert_roi(cert)
        out_fmt = str(args.get("format", "markdown")).lower()

        if out_fmt == "json":
            return json.dumps(analysis.to_dict(), indent=2)

        return (
            f"### 💰 Certification ROI & Value Analysis: {analysis.title}\n\n"
            f"- **Provider / Level:** `{analysis.provider}` ({analysis.level})\n"
            f"- **Exam Cost:** `${analysis.exam_cost_usd:.2f}`\n"
            f"- **Study Commitment:** `{analysis.estimated_study_hours}` hours\n"
            f"- **Projected Annual Salary Premium:** `${analysis.annual_salary_premium_usd:,.2f}/year`\n"
            f"- **Payback Horizon:** `{analysis.payback_period_months:.1f} months`\n"
            f"- **Study Hourly Return:** `${analysis.hourly_study_value_usd:.2f}/hour`\n"
            f"- **5-Year Net ROI:** `${analysis.five_year_net_gain_usd:,.2f}` (`{analysis.five_year_roi_pct:,.0f}%`)\n"
            f"- **Market Demand Rating:** **{analysis.market_demand_rating}**\n\n"
            f"```text\n{format_roi_scorecard(analysis)}\n```"
        )

    def _tool_skill_overlap(self, args: Dict[str, Any]) -> str:
        """Handler for certpath_skill_overlap."""
        from .roi_calculator import calculate_skill_overlap

        cert_a_id = args.get("cert_a_id", "").strip()
        cert_b_id = args.get("cert_b_id", "").strip()
        if not cert_a_id or not cert_b_id:
            return "Error: Parameters 'cert_a_id' and 'cert_b_id' are both required."

        cert_a = self.catalog.get(cert_a_id) or (self.catalog.search(query=cert_a_id) or [None])[0]
        cert_b = self.catalog.get(cert_b_id) or (self.catalog.search(query=cert_b_id) or [None])[0]

        if not cert_a:
            return f"Error: Certification '{cert_a_id}' not found in catalog."
        if not cert_b:
            return f"Error: Certification '{cert_b_id}' not found in catalog."

        overlap = calculate_skill_overlap(cert_a, cert_b)
        out_fmt = str(args.get("format", "markdown")).lower()

        if out_fmt == "json":
            return json.dumps(overlap.to_dict(), indent=2)

        lines = [
            f"### 🔀 Skill & Competency Overlap: {cert_a.title} ⟷ {cert_b.title}",
            "",
            f"- **Competency Overlap Index:** `{overlap.overlap_ratio * 100:.1f}%`",
            f"- **Synergistic Study Discount:** `{overlap.synergy_discount_pct:.1f}%`",
            f"- **Study Hours Saved on '{cert_b.title}':** `{overlap.study_hours_saved} hours`",
            "",
            f"#### 🤝 Shared Competencies & Knowledge Domains ({len(overlap.shared_skills)}):",
        ]
        for s in overlap.shared_skills[:10]:
            lines.append(f"- `{s}`")
        if len(overlap.shared_skills) > 10:
            lines.append(f"- *...and {len(overlap.shared_skills) - 10} more*")

        lines.append("")
        lines.append(f"#### 🎯 Unique to {cert_a.title} ({len(overlap.unique_to_a)}):")
        for s in overlap.unique_to_a[:6]:
            lines.append(f"- {s}")

        lines.append("")
        lines.append(f"#### 🎯 Unique to {cert_b.title} ({len(overlap.unique_to_b)}):")
        for s in overlap.unique_to_b[:6]:
            lines.append(f"- {s}")

        return "\n".join(lines)

    def _tool_portfolio_valuation(self, args: Dict[str, Any]) -> str:
        """Handler for certpath_portfolio_valuation."""
        from .roi_calculator import evaluate_portfolio, format_portfolio_scorecard

        cert_ids = args.get("cert_ids", [])
        if not isinstance(cert_ids, list) or not cert_ids:
            return "Error: Parameter 'cert_ids' must be a non-empty list of certification IDs."

        val = evaluate_portfolio(cert_ids, catalog=self.catalog)
        out_fmt = str(args.get("format", "markdown")).lower()

        if out_fmt == "json":
            return json.dumps(val.to_dict(), indent=2)

        min_sal, max_sal = val.estimated_salary_range_usd
        lines = [
            f"### 🏛️ Credential Portfolio Valuation & Market Power Scorecard",
            "",
            f"- **Evaluated Credentials:** `{val.total_credentials}` credentials",
            f"- **Total Direct Exam Investment:** `${val.total_investment_cost_usd:,.2f}`",
            f"- **Total Cumulative Study Hours:** `{val.total_study_hours_invested}` hours",
            f"- **Projected Cumulative Earning Premium:** `${val.total_annual_salary_potential_usd:,.2f}/year`",
            f"- **Estimated Market Salary Range:** **${min_sal:,} - ${max_sal:,} USD**",
            f"- **Composite Marketability Index:** `{val.composite_marketability_index:.1f}/100`",
            f"- **Vendor Diversification Score:** `{val.vendor_diversification_score:.1f}/100`",
            f"- **Multi-Cloud Readiness Quotient:** `{val.multi_cloud_score:.1f}/100`",
            f"- **Security Posture Quotient:** `{val.security_quotient:.1f}/100`",
            "",
            f"```text\n{format_portfolio_scorecard(val)}\n```",
        ]
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # JSON-RPC 2.0 Protocol Dispatcher
    # -------------------------------------------------------------------------

    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single JSON-RPC 2.0 request or notification and return response."""
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if not method or not isinstance(method, str):
            if req_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32600, "message": "Invalid Request: method is required"},
                }
            return None

        # 1. MCP initialize handshake
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION,
                    },
                    "capabilities": {
                        "tools": {},
                    },
                },
            }

        # 2. Notification for initialized
        if method in ("notifications/initialized", "initialized"):
            return None

        # 3. Ping
        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        # 4. tools/list
        if method == "tools/list":
            tools_list = list(self._tools.values())
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools_list},
            }

        # 5. tools/call
        if method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})

            if not tool_name or tool_name not in self._handlers:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error: Unknown tool '{tool_name}'. Available: {', '.join(self._handlers.keys())}",
                            }
                        ],
                        "isError": True,
                    },
                }

            handler = self._handlers[tool_name]
            try:
                result_text = handler(tool_args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": str(result_text)}],
                        "isError": False,
                    },
                }
            except Exception as err:
                tb = traceback.format_exc()
                _log_stderr(f"Error executing tool '{tool_name}': {err}\n{tb}")
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Execution Error in '{tool_name}': {str(err)}",
                            }
                        ],
                        "isError": True,
                    },
                }

        # Unknown method
        if req_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: '{method}'",
                },
            }
        return None

    def run(self) -> None:
        """Run the MCP server reading from sys.stdin and writing to sys.stdout."""
        self._running = True
        _log_stderr(f"Starting {SERVER_NAME} v{SERVER_VERSION} over stdio transport...")

        # Setup graceful signal handlers
        def signal_handler(signum, frame):
            _log_stderr("Received termination signal, shutting down.")
            self._running = False
            sys.exit(0)

        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        except (ValueError, AttributeError):
            # Running in environments where signal handling is restricted
            pass

        while self._running:
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                line_str = line.strip()
                if not line_str:
                    continue

                # Support optional Content-Length framing if present
                if line_str.lower().startswith("content-length:"):
                    try:
                        length = int(line_str.split(":", 1)[1].strip())
                        # Read blank line
                        sys.stdin.readline()
                        body = sys.stdin.read(length)
                        data = json.loads(body)
                    except Exception as parse_err:
                        _log_stderr(f"Framed message parse error: {parse_err}")
                        continue
                else:
                    try:
                        data = json.loads(line_str)
                    except json.JSONDecodeError as json_err:
                        _log_stderr(f"JSON decode error: {json_err} for payload: {line_str[:100]}")
                        err_response = {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {"code": -32700, "message": "Parse error"},
                        }
                        sys.stdout.write(json.dumps(err_response) + "\n")
                        sys.stdout.flush()
                        continue

                if isinstance(data, dict):
                    response = self.handle_request(data)
                    if response is not None:
                        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                        sys.stdout.flush()
                elif isinstance(data, list):
                    # Batch request handling
                    batch_responses = []
                    for single_req in data:
                        if isinstance(single_req, dict):
                            res = self.handle_request(single_req)
                            if res is not None:
                                batch_responses.append(res)
                    if batch_responses:
                        sys.stdout.write(json.dumps(batch_responses, ensure_ascii=False) + "\n")
                        sys.stdout.flush()

            except (IOError, KeyboardInterrupt):
                break
            except Exception as loop_err:
                _log_stderr(f"Unexpected server loop error: {loop_err}\n{traceback.format_exc()}")

        _log_stderr("MCP server terminated.")


def main() -> None:
    """CLI entry point for running the MCP server directly."""
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
