"""Command-line interface (CLI) for CertPath Roadmap Studio.

Multi-OS CLI supporting certification search, DAG prerequisite resolution,
personalized career roadmap planning, side-by-side comparisons, visual exports,
local web UI serving, and MCP server execution.

Zero third-party runtime dependencies (100% Python Standard Library).
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import platform
import socket
import socketserver
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .catalog import Certification, CertificationCatalog
from .compat import get_platform_name, normalize_path
from .dag_engine import DAGEngine
from .matrix_exporter import (
    export_ascii_tree,
    export_json_ld,
    export_markdown,
    export_mermaid,
)
from .mcp_server import MCPServer
from .roadmap_planner import BUILTIN_ROLES, CareerRole, RoadmapPlan, RoadmapPlanner

__version__ = "0.1.0"


# -----------------------------------------------------------------------------
# Terminal ANSI Color & Formatting Utilities
# -----------------------------------------------------------------------------

class Term:
    """Terminal styling helper with automatic TTY and NO_COLOR detection."""

    _enabled: bool = True

    @classmethod
    def init(cls, force_no_color: bool = False) -> None:
        """Initialize color support based on stdout TTY state and environment."""
        no_color_env = "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb"
        cls._enabled = sys.stdout.isatty() and not no_color_env and not force_no_color

    @classmethod
    def style(cls, text: str, code: str) -> str:
        """Wrap text in ANSI escape code if enabled."""
        if not cls._enabled or not text:
            return text
        return f"\033[{code}m{text}\033[0m"

    @classmethod
    def bold(cls, text: str) -> str:
        return cls.style(text, "1")

    @classmethod
    def dim(cls, text: str) -> str:
        return cls.style(text, "2")

    @classmethod
    def cyan(cls, text: str) -> str:
        return cls.style(text, "36")

    @classmethod
    def green(cls, text: str) -> str:
        return cls.style(text, "32")

    @classmethod
    def yellow(cls, text: str) -> str:
        return cls.style(text, "33")

    @classmethod
    def blue(cls, text: str) -> str:
        return cls.style(text, "34")

    @classmethod
    def magenta(cls, text: str) -> str:
        return cls.style(text, "35")

    @classmethod
    def red(cls, text: str) -> str:
        return cls.style(text, "31")

    @classmethod
    def white(cls, text: str) -> str:
        return cls.style(text, "37")


def format_table(headers: List[str], rows: List[List[str]]) -> str:
    """Render a clean ASCII table with proper column alignment."""
    if not rows:
        return "No data to display."

    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            if idx < len(col_widths):
                col_widths[idx] = max(col_widths[idx], len(str(cell)))

    # Header
    header_cells = [Term.bold(headers[i].ljust(col_widths[i])) for i in range(len(headers))]
    header_line = " | ".join(header_cells)
    divider_line = "-+-".join("-" * w for w in col_widths)

    lines = [header_line, divider_line]
    for row in rows:
        row_cells = []
        for i in range(len(headers)):
            val = str(row[i]) if i < len(row) else ""
            row_cells.append(val.ljust(col_widths[i]))
        lines.append(" | ".join(row_cells))

    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Subcommand Handlers
# -----------------------------------------------------------------------------

def cmd_search(args: argparse.Namespace, catalog: CertificationCatalog) -> int:
    """Search certification catalog by keyword, provider, level, or skill."""
    query = args.query if args.query else None
    results = catalog.search(
        query=query,
        provider=args.provider,
        level=args.level,
        category=args.category,
        skill=args.skill,
        interest=args.interest,
        max_cost=args.max_cost,
        max_hours=args.max_hours,
    )
    sliced = results[: args.limit]

    if args.json:
        print(json.dumps([c.to_dict() for c in sliced], indent=2))
        return 0

    print(Term.bold(f"\n🔍 Found {len(results)} certifications (showing top {len(sliced)}):\n"))
    if not sliced:
        print(Term.yellow("No certifications matched your criteria."))
        return 0

    headers = ["ID", "Title", "Provider", "Level", "Category", "Hours", "Fee", "Exam"]
    rows = []
    for c in sliced:
        fee = f"${c.cost_usd:.0f}" if c.cost_usd > 0 else "Free"
        rows.append([
            c.id,
            c.title[:38] + ("..." if len(c.title) > 38 else ""),
            c.provider[:18],
            c.level,
            c.category[:20],
            f"{c.estimated_hours}h",
            fee,
            c.exam_code or "-",
        ])

    print(format_table(headers, rows))
    print(Term.dim(f"\nTip: Run 'certpath prereqs <id>' or 'certpath tree <id>' to inspect prerequisites.\n"))
    return 0


def cmd_prereqs(args: argparse.Namespace, catalog: CertificationCatalog, dag: DAGEngine) -> int:
    """Output complete prerequisite chain in topological sequence."""
    cert_id = args.cert_id.strip()
    target = catalog.get_by_id(cert_id)
    if not target:
        print(Term.red(f"Error: Certification '{cert_id}' not found in catalog."), file=sys.stderr)
        return 1

    chain = dag.resolve_prerequisites(cert_id, include_target=args.include_target)
    depth = dag.get_depth(cert_id)
    difficulty = dag.difficulty_score(cert_id)
    dependents = dag.resolve_dependents(cert_id, include_self=False)

    total_hours = sum(c.estimated_hours for c in chain)
    total_cost = sum(c.cost_usd for c in chain)

    if args.json:
        print(json.dumps([c.to_dict() for c in chain], indent=2))
        return 0

    print(Term.bold(f"\n🎯 Target: {target.title} ({target.provider})"))
    print(Term.dim(f"   ID: {target.id} | Level: {target.level} | Difficulty: {difficulty:.1f}/15.0 | Depth: {depth} hops"))
    print(Term.dim(f"   Total Effort: {total_hours}h | Exam Fees: ${total_cost:,.2f} USD\n"))

    if not chain or (len(chain) == 1 and chain[0].id == cert_id and not args.include_target):
        print(Term.green("🎉 No prerequisites required! This is a foundational root credential."))
    else:
        print(Term.bold("📋 Recommended Study Sequence (Topological Order):"))
        for idx, c in enumerate(chain, start=1):
            is_target = c.id == cert_id
            marker = Term.yellow(" ◄ (Target Goal)") if is_target else ""
            fee = f"${c.cost_usd:.0f}" if c.cost_usd > 0 else "Free"
            code = f" [{c.exam_code}]" if c.exam_code else ""
            print(f"  {Term.bold(str(idx))}. {Term.cyan(c.title)} ({c.id}){code}{marker}")
            print(f"     {Term.dim(c.provider + ' • ' + c.level + ' • ' + str(c.estimated_hours) + 'h • ' + fee)}")
            if c.skills_gained:
                print(f"     Skills: {Term.dim(', '.join(c.skills_gained[:5]))}")

    if dependents:
        print(Term.bold(f"\n🔓 Unlocked Next Steps ({len(dependents)} credentials):"))
        for d in dependents[:5]:
            d_fee = f"${d.cost_usd:.0f}" if d.cost_usd > 0 else "Free"
            print(f"  • {Term.green(d.title)} ({d.id}) - {d.provider} ({d.level}, {d_fee})")
    print()
    return 0


def cmd_unlocked(args: argparse.Namespace, catalog: CertificationCatalog, dag: DAGEngine) -> int:
    """Output all certifications unlocked directly or transitively by acquiring a credential."""
    cert_id = args.cert_id.strip()
    target = catalog.get_by_id(cert_id)
    if not target:
        print(Term.red(f"Error: Certification '{cert_id}' not found in catalog."), file=sys.stderr)
        return 1

    dependents = dag.resolve_dependents(cert_id, include_self=False)
    if args.json:
        print(json.dumps([d.to_dict() for d in dependents], indent=2))
        return 0

    print(Term.bold(f"\n🔓 Certifications Unlocked by '{target.title}' ({target.id}):\n"))
    if not dependents:
        print(Term.yellow("No downstream certifications found. This is a capstone landmark credential."))
        return 0

    headers = ["ID", "Title", "Provider", "Level", "Category", "Hours", "Fee"]
    rows = []
    for d in dependents:
        fee = f"${d.cost_usd:.0f}" if d.cost_usd > 0 else "Free"
        rows.append([d.id, d.title[:38], d.provider[:18], d.level, d.category[:20], f"{d.estimated_hours}h", fee])

    print(format_table(headers, rows))
    print()
    return 0


def cmd_plan(args: argparse.Namespace, planner: RoadmapPlanner) -> int:
    """Generate customized career roadmap from current level to target role/cert."""
    target_identifier = args.role or args.target or "cloud_security_architect"
    current_certs: List[str] = []
    if args.current:
        for c_item in args.current:
            current_certs.extend([x.strip() for x in c_item.split(",") if x.strip()])

    hours_per_week = max(1, args.hours_per_week)
    max_budget = float(args.max_budget) if args.max_budget is not None else None
    fmt = args.format.lower()

    try:
        plan: RoadmapPlan = planner.generate_roadmap(
            target_role_or_cert=target_identifier,
            current_certs=current_certs,
            weekly_hours=hours_per_week,
            max_budget=max_budget,
        )
    except Exception as err:
        print(Term.red(f"Error generating roadmap plan: {err}"), file=sys.stderr)
        return 1

    if fmt == "json":
        print(json.dumps(plan.to_dict(), indent=2))
        return 0
    elif fmt in ("md", "markdown"):
        print(export_markdown(plan, include_resources=True))
        return 0
    elif fmt == "mermaid":
        print(export_mermaid(plan, direction="LR", group_by="phase"))
        return 0

    # Text format
    print(Term.bold(f"\n🗺️ Career Roadmap: {plan.target_name}"))
    print(Term.dim(f"   Pace: {plan.weekly_hours} hrs/week | Total Duration: ~{plan.total_weeks:.1f} weeks ({plan.total_weeks/4.33:.1f} months)"))
    print(Term.dim(f"   Total Effort: {plan.total_hours} hours | Exam Fees: ${plan.total_cost_usd:,.2f} USD | Total Certs: {len(plan.all_certifications)}\n"))

    if plan.budget_exceeded:
        print(Term.red(f"⚠️ Warning: Total exam cost (${plan.total_cost_usd:,.2f}) exceeds specified budget of ${plan.max_budget:,.2f}\n"))

    print(Term.bold("🎯 Milestone Study Path:"))
    for m in plan.milestones:
        fee = f"${m.cost_usd:.0f}" if m.cost_usd > 0 else "Free"
        code = f" [{m.exam_code}]" if m.exam_code else ""
        print(f"  [{m.index}] {Term.cyan(m.title)} ({m.cert_id}){code}")
        print(f"      Phase: {m.phase_name} • Week {m.target_week:.1f} • {m.estimated_hours}h • {fee}")
        if m.skills_unlocked:
            print(f"      Skills: {Term.dim(', '.join(m.skills_unlocked[:5]))}")

    print(Term.bold("\n📚 Multi-Phase Breakdown:"))
    for p in plan.phases:
        print(f"\n  • {Term.yellow(p.phase_name)} ({p.estimated_hours}h, ${p.cost_usd:.0f})")
        print(f"    {Term.dim(p.description)}")
        for cert in p.certifications:
            c_fee = f"${cert.cost_usd:.0f}" if cert.cost_usd > 0 else "Free"
            print(f"    - {cert.title} ({cert.provider}, {cert.estimated_hours}h, {c_fee})")

    print(Term.dim(f"\nTip: Use '--format md' to generate a full Markdown guide or '--format mermaid' for flowcharts.\n"))
    return 0


def cmd_compare(args: argparse.Namespace, catalog: CertificationCatalog, dag: DAGEngine) -> int:
    """Side-by-side comparison table of 2+ certifications."""
    cert_ids = args.cert_ids
    if len(cert_ids) < 2:
        print(Term.red("Error: Please provide at least 2 certification IDs to compare."), file=sys.stderr)
        return 1

    certs: List[Certification] = []
    for cid in cert_ids:
        c = catalog.get_by_id(cid.strip())
        if not c:
            print(Term.red(f"Error: Certification '{cid}' not found in catalog."), file=sys.stderr)
            return 1
        certs.append(c)

    if args.json:
        data = []
        for c in certs:
            data.append({
                "cert": c.to_dict(),
                "difficulty_score": dag.difficulty_score(c.id),
                "prerequisite_depth": dag.get_depth(c.id),
                "total_prereqs": len(dag.resolve_prerequisites(c.id, include_target=False)),
            })
        print(json.dumps(data, indent=2))
        return 0

    print(Term.bold(f"\n⚖️ Side-by-Side Comparison ({len(certs)} Credentials):\n"))
    headers = ["Feature"] + [c.title[:25] for c in certs]
    rows = [
        ["ID"] + [c.id for c in certs],
        ["Provider"] + [c.provider for c in certs],
        ["Level"] + [c.level for c in certs],
        ["Category"] + [c.category for c in certs],
        ["Exam Code"] + [c.exam_code or "—" for c in certs],
        ["Study Hours"] + [f"{c.estimated_hours}h" for c in certs],
        ["Exam Fee"] + [f"${c.cost_usd:.0f}" if c.cost_usd > 0 else "Free" for c in certs],
        ["Difficulty"] + [f"{dag.difficulty_score(c.id):.1f}/15" for c in certs],
        ["Prereq Depth"] + [f"{dag.get_depth(c.id)} hops" for c in certs],
        ["Prerequisites"] + [", ".join(c.prerequisites) or "None (Root)" for c in certs],
    ]
    print(format_table(headers, rows))

    print(Term.bold("\n🎯 Skills Breakdown:"))
    for c in certs:
        print(f"  • {Term.cyan(c.title)}: {Term.dim(', '.join(c.skills_gained))}")

    all_sets = [set(c.skills_gained) for c in certs]
    overlap = set.intersection(*all_sets) if all_sets else set()
    if overlap:
        print(Term.bold(f"\n🤝 Shared Overlapping Skills: {Term.green(', '.join(sorted(overlap)))}\n"))
    else:
        print()
    return 0


def cmd_simulate(args: argparse.Namespace, planner: RoadmapPlanner) -> int:
    """Handle 'simulate' / 'velocity' subcommand with Monte Carlo and burnout modeling."""
    from .velocity_simulator import simulate_velocity

    target_identifier = getattr(args, "role", None) or getattr(args, "target", None) or "cloud_security_architect"
    current_certs: List[str] = []
    if getattr(args, "current", None):
        for c_item in args.current:
            current_certs.extend([x.strip() for x in c_item.split(",") if x.strip()])

    hours = float(getattr(args, "hours", 10.0))
    exp_lvl = str(getattr(args, "experience", "intermediate"))
    trials = int(getattr(args, "trials", 500))

    try:
        plan = planner.generate_roadmap(
            target_role_or_cert=target_identifier,
            current_certs=current_certs,
            weekly_hours=int(hours),
        )
        report = simulate_velocity(
            plan_or_certs=plan,
            weekly_hours=hours,
            experience_level=exp_lvl,
            simulation_trials=trials,
        )
    except Exception as err:
        print(Term.red(f"Error simulating velocity: {err}"), file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
        return 0

    mc = report.monte_carlo
    color_risk = Term.red if report.fatigue_index >= 70 else (Term.yellow if report.fatigue_index >= 45 else Term.green)

    print(Term.bold(f"\n🚀 Learning Velocity & Monte Carlo Schedule Simulation: {report.target_name}"))
    print(Term.dim(f"   Learner Tier: {report.experience_level.title()} ({report.learning_speed_multiplier:.2f}x speed) | Study Pace: {report.weekly_hours:.0f} hrs/week"))
    print(Term.dim(f"   Effort: {report.total_nominal_hours}h nominal -> {report.total_adjusted_hours:.1f}h adjusted | Cognitive Fatigue Index: ") + color_risk(f"{report.fatigue_index:.1f}/100\n"))

    print(Term.bold("🎲 Monte Carlo Probabilistic Completion Milestones (500 Stochastic Trials):"))
    mc_rows = [
        ["P50 (Median)", f"{mc.weeks_p50:.1f} weeks (~{mc.weeks_p50/4.33:.1f} mo)", mc.completion_date_p50, f"${mc.cost_p50:,.2f}", f"{mc.retakes_p50:.1f}"],
        ["P80 (Realistic)", f"{mc.weeks_p80:.1f} weeks (~{mc.weeks_p80/4.33:.1f} mo)", mc.completion_date_p80, f"${mc.cost_p80:,.2f}", "-"],
        ["P95 (Conservative)", f"{mc.weeks_p95:.1f} weeks (~{mc.weeks_p95/4.33:.1f} mo)", mc.completion_date_p95, f"${mc.cost_p95:,.2f}", f"{mc.retakes_p95:.1f}"],
    ]
    print(format_table(["Confidence Tier", "Timeline Duration", "Target Date", "Est. Budget", "Retakes"], mc_rows))
    print()

    if report.fatigue_warnings:
        print(Term.yellow("⚠️ Cognitive Fatigue & Burnout Alerts:"))
        for w in report.fatigue_warnings:
            print(f"  {Term.red(f'[{w.risk_level}]')} {Term.bold(w.title)}: {w.recommendation}")
        print()

    print(Term.bold("📅 Milestone Study Timeline Sequence:"))
    m_rows = []
    for m in report.milestones:
        m_rows.append([
            str(m.index),
            m.title,
            m.level,
            f"{m.adjusted_hours:.0f}h",
            f"{m.estimated_weeks:.1f}w",
            m.completion_date_iso,
            f"{m.pass_probability*100:.0f}%",
        ])
    print(format_table(["#", "Certification", "Level", "Hours", "Weeks", "Target Date", "Pass Prob"], m_rows))
    print()

    print(Term.cyan(report.ascii_burndown_chart))
    print()
    return 0


def cmd_roi(args: argparse.Namespace, catalog: CertificationCatalog, planner: RoadmapPlanner) -> int:
    """Analyze certification financial ROI, salary impact, and portfolio market value."""
    from .roi_calculator import (
        calculate_cert_roi,
        evaluate_portfolio,
        format_portfolio_scorecard,
        format_roi_scorecard,
    )

    # 1. Single certification ROI mode
    if getattr(args, "cert", None):
        cid = args.cert.strip()
        cert = catalog.get(cid) or (catalog.search(query=cid) or [None])[0]
        if not cert:
            print(Term.red(f"Error: Certification '{cid}' not found in catalog."), file=sys.stderr)
            return 1

        analysis = calculate_cert_roi(cert)
        if getattr(args, "json", False):
            print(json.dumps(analysis.to_dict(), indent=2))
            return 0

        print()
        print(Term.cyan(format_roi_scorecard(analysis)))
        print()
        return 0

    # 2. Portfolio / Role valuation mode
    cert_ids: List[str] = []
    if getattr(args, "portfolio", None):
        for item in args.portfolio:
            cert_ids.extend([x.strip() for x in item.split(",") if x.strip()])
    elif getattr(args, "role", None):
        role_plan = planner.generate_roadmap(args.role)
        cert_ids = [c.id for c in role_plan.all_certifications]
    else:
        # Default to cloud_solutions_architect role
        role_plan = planner.generate_roadmap("cloud_solutions_architect")
        cert_ids = [c.id for c in role_plan.all_certifications]

    val = evaluate_portfolio(cert_ids, catalog=catalog)
    if getattr(args, "json", False):
        print(json.dumps(val.to_dict(), indent=2))
        return 0

    print()
    print(Term.cyan(format_portfolio_scorecard(val)))
    print()
    return 0


def cmd_overlap(args: argparse.Namespace, catalog: CertificationCatalog) -> int:
    """Quantify knowledge transfer and skill overlap between two certifications."""
    from .roi_calculator import calculate_skill_overlap

    cid_a = args.cert_a.strip()
    cid_b = args.cert_b.strip()

    c_a = catalog.get(cid_a) or (catalog.search(query=cid_a) or [None])[0]
    c_b = catalog.get(cid_b) or (catalog.search(query=cid_b) or [None])[0]

    if not c_a:
        print(Term.red(f"Error: First certification '{cid_a}' not found."), file=sys.stderr)
        return 1
    if not c_b:
        print(Term.red(f"Error: Second certification '{cid_b}' not found."), file=sys.stderr)
        return 1

    overlap = calculate_skill_overlap(c_a, c_b)
    if getattr(args, "json", False):
        print(json.dumps(overlap.to_dict(), indent=2))
        return 0

    print(Term.bold(f"\n🔀 Skill & Competency Overlap: {c_a.title} ⟷ {c_b.title}"))
    print(f"  • {Term.bold('Competency Overlap Index:')} {Term.cyan(f'{overlap.overlap_ratio * 100:.1f}%')}")
    print(f"  • {Term.bold('Synergy Discount:')}        {Term.green(f'{overlap.synergy_discount_pct:.1f}%')} off study duration")
    print(f"  • {Term.bold('Study Hours Saved:')}        {Term.green(f'{overlap.study_hours_saved} hours')} saved on {c_b.title}\n")

    if overlap.shared_skills:
        print(Term.bold(f"🤝 Shared Competencies ({len(overlap.shared_skills)}):"))
        for s in overlap.shared_skills[:8]:
            print(f"  {Term.green('✓')} {s}")
        if len(overlap.shared_skills) > 8:
            print(f"  {Term.dim(f'...and {len(overlap.shared_skills) - 8} more')}")
        print()

    print(Term.bold(f"🎯 Distinct Skills in {c_a.title}:"))
    for s in overlap.unique_to_a[:4]:
        print(f"  • {s}")
    print()

    print(Term.bold(f"🎯 Distinct Skills in {c_b.title}:"))
    for s in overlap.unique_to_b[:4]:
        print(f"  • {s}")
    print()
    return 0


def cmd_mermaid(args: argparse.Namespace, catalog: CertificationCatalog, dag: DAGEngine) -> int:
    """Output Mermaid flowchart syntax."""
    target_str = args.target
    direction = args.direction.upper()

    if args.full:
        print(export_mermaid(catalog, direction=direction, group_by="category"))
        return 0

    if not target_str:
        # Export default catalog
        print(export_mermaid(catalog, direction=direction, group_by="category"))
        return 0

    # Check if target is a certification ID
    cert = catalog.get_by_id(target_str)
    if cert:
        chain = dag.resolve_prerequisites(target_str, include_target=True)
        print(export_mermaid(chain, direction=direction, group_by="none"))
        return 0

    # Check if target is a category
    categories = {c.category.lower(): c.category for c in catalog.get_all()}
    if target_str.lower() in categories:
        cat_name = categories[target_str.lower()]
        cat_certs = [c for c in catalog.get_all() if c.category == cat_name]
        print(export_mermaid(cat_certs, direction=direction, group_by="none"))
        return 0

    # Check if target is a role ID
    if target_str in BUILTIN_ROLES:
        planner = RoadmapPlanner(catalog, dag)
        plan = planner.generate_roadmap(target_str)
        print(export_mermaid(plan, direction=direction, group_by="phase"))
        return 0

    print(Term.red(f"Error: Target '{target_str}' is neither a valid certification ID, category, nor role."), file=sys.stderr)
    return 1


def cmd_tree(args: argparse.Namespace, catalog: CertificationCatalog, dag: DAGEngine) -> int:
    """Output ASCII prerequisite tree."""
    cert_id = args.cert_id.strip()
    target = catalog.get_by_id(cert_id)
    if not target:
        print(Term.red(f"Error: Certification '{cert_id}' not found in catalog."), file=sys.stderr)
        return 1

    print(export_ascii_tree(
        target_id=cert_id,
        catalog=catalog,
        dag_engine=dag,
        show_dependents=not args.no_dependents,
    ))
    return 0


def cmd_roles(args: argparse.Namespace, planner: RoadmapPlanner) -> int:
    """List built-in career role templates."""
    roles = planner.get_roles()
    if args.category:
        roles = [r for r in roles if r.category.lower() == args.category.lower().strip()]

    if args.json:
        print(json.dumps([r.to_dict() for r in roles], indent=2))
        return 0

    print(Term.bold(f"\n💼 Career Role Templates ({len(roles)} Archetypes):\n"))
    headers = ["Role ID", "Title", "Category", "Target Certs", "Target Level"]
    rows = []
    for r in roles:
        targets = ", ".join(r.target_certs[:3]) + ("..." if len(r.target_certs) > 3 else "")
        rows.append([r.role_id, r.title, r.category, targets, r.target_level])

    print(format_table(headers, rows))
    print(Term.dim("\nTip: Run 'certpath plan --role <role_id>' to generate a full roadmap.\n"))
    return 0


def cmd_stats(args: argparse.Namespace, catalog: CertificationCatalog, dag: DAGEngine) -> int:
    """Output catalog telemetry."""
    stats = catalog.summary_statistics()
    is_dag = dag.is_dag()
    cycles = dag.detect_cycles()
    roots = dag.get_roots()
    leaves = dag.get_leaves()

    data = {
        **stats,
        "is_dag": is_dag,
        "is_strict_dag": is_dag,
        "cycles_count": len(cycles),
        "root_certifications_count": len(roots),
        "leaf_certifications_count": len(leaves),
    }

    if args.json:
        if args.verbose:
            data["root_ids"] = [r.id for r in roots]
            data["leaf_ids"] = [l.id for l in leaves]
        print(json.dumps(data, indent=2))
        return 0

    print(Term.bold("\n📊 CertPath Catalog Statistics & DAG Telemetry:\n"))
    print(f"  • {Term.bold('Total Certifications:')} {Term.cyan(str(stats['total_certs']))}")
    print(f"  • {Term.bold('Unique Skills Indexed:')} {Term.cyan(str(stats['total_skills']))}")
    print(f"  • {Term.bold('Average Study Hours:')} {stats['average_hours']}h per credential")
    print(f"  • {Term.bold('Average Exam Fee:')} ${stats['average_cost']:.2f} USD")
    print(f"  • {Term.bold('Free Credentials:')} {stats['free_certs_count']} credentials")
    print(f"  • {Term.bold('DAG Acyclicity:')} {Term.green('Valid DAG (Strictly Acyclic)') if is_dag else Term.red('Contains Cycles')}")
    print(f"  • {Term.bold('Root Entry Points:')} {len(roots)} certs with no prerequisites")
    print(f"  • {Term.bold('Capstone Credentials:')} {len(leaves)} terminal certs\n")

    print(Term.bold("📁 Category Distribution:"))
    for cat, cnt in stats["by_category"].items():
        bar = "█" * (cnt // 2)
        print(f"  {cat.ljust(25)} : {str(cnt).rjust(3)}  {Term.dim(bar)}")

    print(Term.bold("\n🏢 Top Providers:"))
    for prov, cnt in list(stats["by_provider"].items())[:8]:
        bar = "█" * (cnt // 2)
        print(f"  {prov.ljust(25)} : {str(cnt).rjust(3)}  {Term.dim(bar)}")
    print()
    return 0


def _find_public_dir() -> Path:
    """Locate the public static directory for web server."""
    current_file = Path(__file__).resolve()
    candidates = [
        current_file.parent.parent.parent / "public",
        current_file.parent / "public",
        Path.cwd() / "public",
    ]
    for p in candidates:
        if p.exists() and p.is_dir() and (p / "index.html").exists():
            return p
    # Fallback to current parent parent
    return current_file.parent.parent.parent / "public"


def cmd_serve(args: argparse.Namespace) -> int:
    """Launch the Google Material 3 Roadmap Studio Web UI."""
    public_dir = _find_public_dir()
    if not public_dir.exists():
        print(Term.red(f"Error: Public web directory not found at {public_dir}"), file=sys.stderr)
        return 1

    host = args.host
    initial_port = args.port

    # Find free port if requested port is taken
    port = initial_port
    for offset in range(20):
        test_port = initial_port + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, test_port)) != 0:
                port = test_port
                break

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *handler_args, **kwargs):
            super().__init__(*handler_args, directory=str(public_dir), **kwargs)

        def log_message(self, format, *log_args):
            # Quiet logging
            pass

    server_address = (host, port)
    url = f"http://{host}:{port}"

    try:
        httpd = socketserver.TCPServer(server_address, Handler)
    except Exception as err:
        print(Term.red(f"Failed to bind HTTP server to {url}: {err}"), file=sys.stderr)
        return 1

    print(Term.bold(f"\n🚀 Google Material 3 Roadmap Studio Web UI running!"))
    print(f"   Local URL:  {Term.green(Term.bold(url))}")
    print(f"   Directory:  {Term.dim(str(public_dir))}")
    print(Term.dim("   Press Ctrl+C to stop the server.\n"))

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(Term.yellow("\nShutting down web server..."))
    finally:
        httpd.server_close()
    return 0


def cmd_mcp() -> int:
    """Run MCP server over stdio."""
    server = MCPServer()
    server.run()
    return 0


def cmd_diagnostics(args: argparse.Namespace, catalog: CertificationCatalog, dag: DAGEngine, planner: RoadmapPlanner) -> int:
    """Run diagnostics health check and report system status."""
    is_dag = dag.is_dag()
    cycles = dag.detect_cycles()
    roots = dag.get_roots()
    leaves = dag.get_leaves()

    report = {
        "status": "healthy",
        "cli_version": __version__,
        "platform": get_platform_name(),
        "os_name": platform.system(),
        "os_release": platform.release(),
        "os_arch": platform.machine(),
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "working_directory": os.getcwd(),
        "catalog_certs_count": len(catalog),
        "catalog_categories_count": len(catalog.get_categories()),
        "catalog_providers_count": len(catalog.get_providers()),
        "catalog_unique_skills": len(catalog.get_all_skills()),
        "dag_consistency": "Valid DAG (Strictly Acyclic)" if is_dag else "Contains Cycles",
        "dag_is_acyclic": is_dag,
        "dag_cycles_count": len(cycles),
        "dag_root_nodes_count": len(roots),
        "dag_leaf_nodes_count": len(leaves),
        "registered_roles_count": len(planner.get_roles()),
    }

    if getattr(args, "json", False):
        print(json.dumps(report, indent=2))
        return 0

    print(Term.bold("\n🩺 CertPath Studio System Diagnostics:\n"))
    for k, v in report.items():
        key_str = Term.bold(k.replace("_", " ").title().ljust(26))
        val_str = Term.green(str(v)) if v is True or v == "healthy" or "Valid" in str(v) else (Term.red(str(v)) if v is False else str(v))
        print(f"  • {key_str} : {val_str}")
    print()
    return 0


def cmd_test() -> int:
    """Run internal self-verification test suite without external dependencies."""
    print(Term.bold("\n🧪 Running CertPath Roadmap Studio Internal Test Suite...\n"))
    start_time = time.time()
    passed = 0
    failed = 0

    def test(name: str, fn) -> None:
        nonlocal passed, failed
        try:
            fn()
            print(f"  {Term.green('✓ PASS')}  {name}")
            passed += 1
        except Exception as ex:
            print(f"  {Term.red('✗ FAIL')}  {name}: {ex}")
            failed += 1

    # 1. Catalog loading
    catalog = CertificationCatalog()
    def t_catalog_load():
        assert len(catalog) >= 100, f"Expected >= 100 certs, got {len(catalog)}"
        assert len(catalog.get_categories()) >= 5
        assert len(catalog.get_providers()) >= 10
    test("Catalog Loading & Core Data Validation", t_catalog_load)

    # 2. Search filtering
    def t_search():
        amazon_certs = catalog.search(provider="Amazon")
        assert len(amazon_certs) > 0, "Amazon certs search returned empty"
        sec_certs = catalog.search(query="Security")
        assert len(sec_certs) > 0, "Query search returned empty"
    test("Multi-Criteria Search Engine", t_search)

    # 3. DAG Graph Engine
    dag = DAGEngine(catalog)
    def t_dag():
        assert dag.is_dag() is True, "Expected DAG to be strictly acyclic"
        assert len(dag.detect_cycles()) == 0, "Found cyclic dependencies"
        roots = dag.get_roots()
        assert len(roots) > 0, "Expected at least 1 root cert"
    test("DAG Graph Engine & Cycle Detection", t_dag)

    # 4. Prerequisite Resolution
    def t_prereqs():
        sample_cert = "web-fcc-frontend"
        if sample_cert in catalog:
            chain = dag.resolve_prerequisites(sample_cert, include_target=True)
            assert len(chain) >= 2, f"Expected prerequisite chain length >= 2, got {len(chain)}"
            assert chain[-1].id == sample_cert, "Target not last in chain"
    test("Prerequisite Dependency Topological Resolution", t_prereqs)

    # 5. Roadmap Planner
    planner = RoadmapPlanner(catalog, dag)
    def t_planner():
        plan = planner.generate_roadmap("cloud_security_architect", weekly_hours=12)
        assert len(plan.all_certifications) > 0, "Roadmap produced no certs"
        assert len(plan.milestones) > 0, "Roadmap produced no milestones"
        assert plan.total_weeks > 0, "Total weeks must be positive"
    test("Career Roadmap Planner & Milestone Generation", t_planner)

    # 6. Matrix Exporters
    def t_exporters():
        plan = planner.generate_roadmap("cloud_security_architect")
        mermaid_out = export_mermaid(plan)
        assert "flowchart" in mermaid_out, "Mermaid output missing flowchart directive"
        md_out = export_markdown(plan)
        assert "Milestone" in md_out, "Markdown output missing milestones"
        tree_out = export_ascii_tree(plan.all_certifications[-1].id, catalog, dag)
        assert "Target" in tree_out, "ASCII tree output missing Target"
    test("Visual Diagram & Markdown Matrix Exporters", t_exporters)

    # 7. MCP Server Tools Dispatch
    def t_mcp():
        server = MCPServer(catalog, dag, planner)
        assert len(server._tools) >= 8, f"Expected 8 MCP tools, got {len(server._tools)}"
        req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        res = server.handle_request(req)
        assert res is not None and "result" in res, "MCP tools/list failed"
        call_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "certpath_catalog_stats", "arguments": {"format": "json"}},
        }
        call_res = server.handle_request(call_req)
        assert call_res is not None and not call_res["result"].get("isError"), "MCP stats tool call failed"
    test("MCP Server Protocol Handshake & Tool Dispatch", t_mcp)

    # 8. Learning Velocity & Monte Carlo Simulator
    def t_velocity():
        from .velocity_simulator import simulate_velocity
        plan = planner.generate_roadmap("cloud_security_architect", weekly_hours=12)
        report = simulate_velocity(plan, weekly_hours=12, simulation_trials=100)
        assert report.total_nominal_hours > 0
        assert report.monte_carlo.weeks_p50 > 0
        assert len(report.milestones) > 0
        assert len(report.ascii_burndown_chart) > 20
    test("Learning Velocity & Monte Carlo Simulation Engine", t_velocity)

    # 9. ROI & Skill Overlap Matrix Engine
    def t_roi():
        from .roi_calculator import calculate_cert_roi, calculate_skill_overlap, evaluate_portfolio
        cert_aws = catalog.get("cloud-aws-saa") or catalog.get_all()[0]
        roi = calculate_cert_roi(cert_aws)
        assert roi.annual_salary_premium_usd > 0
        assert roi.payback_period_months > 0
        cert_sec = catalog.get("sec-aws-sec-spec") or catalog.get_all()[1]
        ov = calculate_skill_overlap(cert_aws, cert_sec)
        assert ov.overlap_ratio >= 0
        val = evaluate_portfolio([cert_aws.id, cert_sec.id], catalog=catalog)
        assert val.composite_marketability_index > 0
    test("ROI & Skill Overlap Matrix Engine", t_roi)

    duration = time.time() - start_time
    print(Term.bold(f"\nResults: {Term.green(str(passed) + ' passed')}, {Term.red(str(failed) + ' failed')} in {duration:.3f}s\n"))
    return 0 if failed == 0 else 1


# -----------------------------------------------------------------------------
# Main Argument Parser
# -----------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser with all subcommands."""
    # Common arguments inherited by all subcommands so flags like --no-color work anywhere
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--no-color", action="store_true", help="Disable ANSI terminal colors")

    parser = argparse.ArgumentParser(
        prog="certpath",
        description="CertPath Roadmap Studio - Intelligent Certification DAG & Career Pathing System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[common_parser],
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 1. search
    p_search = subparsers.add_parser("search", parents=[common_parser], help="Search certification catalog")
    p_search.add_argument("query", nargs="?", default=None, help="Free-form search text")
    p_search.add_argument("--provider", "-p", help="Filter by provider")
    p_search.add_argument("--level", "-l", choices=["Entry", "Intermediate", "Advanced"], help="Filter by level")
    p_search.add_argument("--category", "-c", help="Filter by category")
    p_search.add_argument("--skill", "-s", help="Filter by skill gained")
    p_search.add_argument("--interest", "-i", help="Filter by interest tag")
    p_search.add_argument("--max-cost", type=float, help="Max exam cost in USD")
    p_search.add_argument("--max-hours", type=int, help="Max study hours")
    p_search.add_argument("--limit", type=int, default=25, help="Result limit (default: 25)")
    p_search.add_argument("--json", action="store_true", help="Output JSON format")

    # 2. prereqs
    p_prereqs = subparsers.add_parser("prereqs", parents=[common_parser], help="Calculate prerequisite study chain")
    p_prereqs.add_argument("cert_id", help="Target certification ID")
    p_prereqs.add_argument("--no-target", dest="include_target", action="store_false", default=True, help="Exclude target cert from chain")
    p_prereqs.add_argument("--json", action="store_true", help="Output JSON format")

    # 3. unlocked
    p_unlocked = subparsers.add_parser("unlocked", parents=[common_parser], help="Show certifications unlocked by a credential")
    p_unlocked.add_argument("cert_id", help="Base certification ID")
    p_unlocked.add_argument("--json", action="store_true", help="Output JSON format")

    # 4. plan
    p_plan = subparsers.add_parser("plan", parents=[common_parser], help="Generate customized career roadmap")
    p_plan.add_argument("--role", "-r", help="Target career role archetype ID")
    p_plan.add_argument("--target", "-t", help="Target certification ID")
    p_plan.add_argument("--current", "-c", action="append", help="Completed cert IDs (comma-separated or multiple)")
    p_plan.add_argument("--hours", "--hours-per-week", "-w", dest="hours_per_week", type=int, default=10, help="Study hours per week (default: 10)")
    p_plan.add_argument("--max-budget", "-b", type=float, help="Max exam fee budget in USD")
    p_plan.add_argument("--format", "-f", choices=["text", "md", "markdown", "json", "mermaid"], default="text", help="Output format (default: text)")

    # 5. compare
    p_compare = subparsers.add_parser("compare", parents=[common_parser], help="Compare 2+ certifications side-by-side")
    p_compare.add_argument("cert_ids", nargs="+", help="Certification IDs to compare")
    p_compare.add_argument("--json", action="store_true", help="Output JSON format")

    # 6. mermaid
    p_mermaid = subparsers.add_parser("mermaid", parents=[common_parser], help="Export Mermaid flowchart syntax")
    p_mermaid.add_argument("target", nargs="?", default=None, help="Certification ID, category, or role ID")
    p_mermaid.add_argument("--direction", "-d", choices=["LR", "TD"], default="LR", help="Flowchart layout (default: LR)")
    p_mermaid.add_argument("--full", action="store_true", help="Export complete catalog graph")

    # 7. tree
    p_tree = subparsers.add_parser("tree", parents=[common_parser], help="Output ASCII prerequisite tree")
    p_tree.add_argument("cert_id", help="Target certification ID")
    p_tree.add_argument("--no-dependents", action="store_true", help="Hide unlocked downstream certs")

    # 8. roles
    p_roles = subparsers.add_parser("roles", parents=[common_parser], help="List career role templates")
    p_roles.add_argument("--category", "-c", help="Filter by category")
    p_roles.add_argument("--json", action="store_true", help="Output JSON format")

    # 9. stats
    p_stats = subparsers.add_parser("stats", parents=[common_parser], help="Output catalog telemetry")
    p_stats.add_argument("--json", action="store_true", help="Output JSON format")
    p_stats.add_argument("--verbose", "-v", action="store_true", help="Show extended telemetry")

    # 10. serve
    p_serve = subparsers.add_parser("serve", parents=[common_parser], help="Launch Google Material 3 Roadmap Studio Web UI")
    p_serve.add_argument("--port", "-p", type=int, default=8080, help="HTTP server port (default: 8080)")
    p_serve.add_argument("--host", default="127.0.0.1", help="HTTP server host (default: 127.0.0.1)")
    p_serve.add_argument("--no-browser", action="store_true", help="Do not automatically open web browser")

    # 11. mcp
    subparsers.add_parser("mcp", parents=[common_parser], help="Run Model Context Protocol (MCP) server over stdio")

    # 12. platform / doctor / diagnostics
    p_diag = subparsers.add_parser("diagnostics", aliases=["doctor", "platform"], parents=[common_parser], help="Run diagnostics report")
    p_diag.add_argument("--json", action="store_true", help="Output JSON format")

    # 13. simulate / velocity
    p_sim = subparsers.add_parser("simulate", aliases=["velocity"], parents=[common_parser], help="Simulate learning velocity & Monte Carlo timeline")
    p_sim.add_argument("--role", "-r", help="Target career role archetype ID")
    p_sim.add_argument("--target", "-t", help="Target certification ID")
    p_sim.add_argument("--current", "-c", action="append", help="Completed cert IDs (comma-separated or multiple)")
    p_sim.add_argument("--hours", "-w", type=float, default=10.0, help="Study hours per week (default: 10)")
    p_sim.add_argument("--experience", "-e", choices=["beginner", "intermediate", "advanced", "expert"], default="intermediate", help="Learner tier (default: intermediate)")
    p_sim.add_argument("--trials", type=int, default=500, help="Monte Carlo trial count (default: 500)")
    p_sim.add_argument("--json", action="store_true", help="Output JSON format")

    # 14. test
    subparsers.add_parser("test", parents=[common_parser], help="Run internal self-verification test suite")

    # 15. roi
    p_roi = subparsers.add_parser("roi", parents=[common_parser], help="Analyze certification financial ROI, salary impact, and portfolio valuation")
    p_roi.add_argument("--cert", "-c", help="Target certification ID for single credential ROI")
    p_roi.add_argument("--role", "-r", help="Target career role archetype for portfolio valuation")
    p_roi.add_argument("--portfolio", "-p", action="append", help="List of cert IDs for portfolio valuation (comma-separated)")
    p_roi.add_argument("--json", action="store_true", help="Output JSON format")

    # 16. overlap
    p_overlap = subparsers.add_parser("overlap", parents=[common_parser], help="Calculate knowledge transfer and skill overlap between two certifications")
    p_overlap.add_argument("cert_a", help="First certification ID")
    p_overlap.add_argument("cert_b", help="Second certification ID")
    p_overlap.add_argument("--json", action="store_true", help="Output JSON format")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    Term.init(force_no_color=args.no_color)

    if not args.command:
        parser.print_help()
        return 0

    # Short-circuit fast commands that don't need full catalog instantiation
    if args.command == "mcp":
        return cmd_mcp()
    if args.command == "serve":
        return cmd_serve(args)
    if args.command == "test":
        return cmd_test()

    # Shared instances
    catalog = CertificationCatalog()
    dag = DAGEngine(catalog)
    planner = RoadmapPlanner(catalog, dag)

    if args.command == "search":
        return cmd_search(args, catalog)
    elif args.command == "prereqs":
        return cmd_prereqs(args, catalog, dag)
    elif args.command == "unlocked":
        return cmd_unlocked(args, catalog, dag)
    elif args.command == "plan":
        return cmd_plan(args, planner)
    elif args.command == "compare":
        return cmd_compare(args, catalog, dag)
    elif args.command == "mermaid":
        return cmd_mermaid(args, catalog, dag)
    elif args.command == "tree":
        return cmd_tree(args, catalog, dag)
    elif args.command == "roles":
        return cmd_roles(args, planner)
    elif args.command == "stats":
        return cmd_stats(args, catalog, dag)
    elif args.command in ("simulate", "velocity"):
        return cmd_simulate(args, planner)
    elif args.command == "roi":
        return cmd_roi(args, catalog, planner)
    elif args.command == "overlap":
        return cmd_overlap(args, catalog)
    elif args.command in ("diagnostics", "doctor", "platform"):
        return cmd_diagnostics(args, catalog, dag, planner)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
