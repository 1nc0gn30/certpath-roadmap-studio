"""Export formats and visual matrix generators for CertPath Roadmap Studio.

Generates:
1. Mermaid Flowchart DAG syntax with color accents and subgraphs.
2. Comprehensive Markdown study guides with milestones and resources.
3. Clean ASCII hierarchy trees of prerequisites and unlockable progressions.
4. Schema.org EducationalOccupationalCredential JSON-LD representations.
Zero third-party dependencies (100% Python Standard Library).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Union

from .catalog import Certification, CertificationCatalog
from .dag_engine import DAGEngine
from .roadmap_planner import RoadmapPhase, RoadmapPlan


def _sanitize_mermaid_id(raw_id: str) -> str:
    """Sanitize certification or phase string into a valid Mermaid node identifier."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", raw_id.strip())
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"n_{cleaned}"
    return cleaned


def _escape_mermaid_label(text: str) -> str:
    """Escape characters for safe inclusion in Mermaid label strings."""
    escaped = text.replace('"', '&quot;').replace("<", "&lt;").replace(">", "&gt;")
    return escaped.replace("\n", " ")


def export_mermaid(
    certs_or_roadmap: Union[RoadmapPlan, Sequence[Certification], CertificationCatalog, Certification],
    direction: str = "LR",
    group_by: str = "auto",  # 'auto', 'phase', 'category', 'provider', 'none'
) -> str:
    """Generate valid, beautifully styled Mermaid flowchart DAG syntax.

    Args:
        certs_or_roadmap: RoadmapPlan, list of Certifications, CertificationCatalog, or single Certification.
        direction: Flowchart orientation: "LR" (left-to-right) or "TD" (top-to-bottom).
        group_by: Subgraph grouping strategy ('auto', 'phase', 'category', 'provider', 'none').
    """
    direction = direction.upper().strip()
    if direction not in ("LR", "TD", "RL", "BT"):
        direction = "LR"

    certs_list: List[Certification] = []
    phases: List[RoadmapPhase] = []
    plan_title: Optional[str] = None

    if isinstance(certs_or_roadmap, RoadmapPlan):
        certs_list = list(certs_or_roadmap.all_certifications)
        phases = list(certs_or_roadmap.phases)
        plan_title = certs_or_roadmap.target_name
        if group_by == "auto":
            group_by = "phase"
    elif isinstance(certs_or_roadmap, CertificationCatalog):
        certs_list = certs_or_roadmap.get_all()
        if group_by == "auto":
            group_by = "category"
    elif isinstance(certs_or_roadmap, (list, tuple)):
        certs_list = [c for c in certs_or_roadmap if isinstance(c, Certification)]
        if group_by == "auto":
            group_by = "category"
    elif isinstance(certs_or_roadmap, Certification):
        certs_list = [certs_or_roadmap]
        if group_by == "auto":
            group_by = "none"

    if not certs_list:
        return f"flowchart {direction}\n    empty[\"No certifications selected\"]\n"

    cert_ids = {c.id for c in certs_list}
    cert_map = {c.id: c for c in certs_list}

    lines: List[str] = [f"flowchart {direction}"]
    if plan_title:
        lines.append(f"    %% Roadmap: {_escape_mermaid_label(plan_title)}")

    # Node rendering helper
    def render_cert_node(cert: Certification, indent: str = "    ") -> str:
        nid = _sanitize_mermaid_id(cert.id)
        title_esc = _escape_mermaid_label(cert.title)
        prov_esc = _escape_mermaid_label(cert.provider)
        lvl_esc = _escape_mermaid_label(cert.level)
        hours = cert.estimated_hours
        cost = f"${cert.cost_usd:.0f}" if cert.cost_usd > 0 else "Free"
        code_tag = f" &bull; {cert.exam_code}" if cert.exam_code else ""

        label = f'<b>{title_esc}</b><br/><small>{prov_esc}{code_tag}<br/>{lvl_esc} &bull; {hours}h &bull; {cost}</small>'
        return f'{indent}{nid}["{label}"]'

    # Grouping by phase
    if group_by == "phase" and phases:
        for p_idx, phase in enumerate(phases, start=1):
            subgraph_id = f"subgraph_phase_{p_idx}"
            subgraph_label = _escape_mermaid_label(phase.phase_name)
            lines.append(f'    subgraph {subgraph_id} ["{subgraph_label}"]')
            for cert in phase.certifications:
                if cert.id in cert_ids:
                    lines.append(render_cert_node(cert, indent="        "))
            lines.append("    end")
    # Grouping by category
    elif group_by == "category":
        categories: Dict[str, List[Certification]] = {}
        for c in certs_list:
            categories.setdefault(c.category, []).append(c)
        for cat_name, cat_certs in sorted(categories.items()):
            subgraph_id = _sanitize_mermaid_id(f"cat_{cat_name}")
            subgraph_label = _escape_mermaid_label(cat_name)
            lines.append(f'    subgraph {subgraph_id} ["{subgraph_label}"]')
            for cert in cat_certs:
                lines.append(render_cert_node(cert, indent="        "))
            lines.append("    end")
    # Grouping by provider
    elif group_by == "provider":
        providers: Dict[str, List[Certification]] = {}
        for c in certs_list:
            providers.setdefault(c.provider, []).append(c)
        for prov_name, prov_certs in sorted(providers.items()):
            subgraph_id = _sanitize_mermaid_id(f"prov_{prov_name}")
            subgraph_label = _escape_mermaid_label(prov_name)
            lines.append(f'    subgraph {subgraph_id} ["{subgraph_label}"]')
            for cert in prov_certs:
                lines.append(render_cert_node(cert, indent="        "))
            lines.append("    end")
    # No subgraphs
    else:
        for cert in certs_list:
            lines.append(render_cert_node(cert, indent="    "))

    lines.append("")
    lines.append("    %% Dependency Connections")

    # Connect edges between certs in current set
    drawn_edges: Set[tuple[str, str]] = set()
    for cert in certs_list:
        src_id = _sanitize_mermaid_id(cert.id)

        # Prerequisites: p -> cert
        for p in cert.prerequisites:
            if p in cert_ids:
                p_nid = _sanitize_mermaid_id(p)
                edge = (p_nid, src_id)
                if edge not in drawn_edges:
                    drawn_edges.add(edge)
                    lines.append(f"    {p_nid} --> {src_id}")

        # Next steps: cert -> n
        for n in cert.next_steps:
            if n in cert_ids:
                n_nid = _sanitize_mermaid_id(n)
                edge = (src_id, n_nid)
                if edge not in drawn_edges:
                    drawn_edges.add(edge)
                    lines.append(f"    {src_id} --> {n_nid}")

    lines.append("")
    lines.append("    %% Node Styling & Color Accents")
    for cert in certs_list:
        nid = _sanitize_mermaid_id(cert.id)
        border_color = cert.color or "#3b82f6"
        lines.append(
            f"    style {nid} fill:#0f172a,stroke:{border_color},stroke-width:2px,color:#f8fafc,rx:6px,ry:6px"
        )

    return "\n".join(lines) + "\n"


def export_markdown(
    roadmap_plan: RoadmapPlan,
    include_resources: bool = True,
) -> str:
    """Generate a comprehensive, beautifully structured Markdown study guide."""
    lines: List[str] = []

    target_title = roadmap_plan.target_name
    type_badge = "Career Role Roadmap" if roadmap_plan.target_type == "role" else "Certification Roadmap"

    lines.append(f"# 🗺️ {target_title}")
    lines.append(f"> **Type:** `{type_badge}` &nbsp;|&nbsp; **Study Pace:** `{roadmap_plan.weekly_hours} hrs/week` &nbsp;|&nbsp; **Total Duration:** `~{roadmap_plan.total_weeks} weeks`")
    lines.append("")

    if roadmap_plan.target_role:
        lines.append(f"**Target Role Description:** {roadmap_plan.target_role.description}")
        lines.append("")

    # Executive Metrics Summary Table
    lines.append("## 📊 Executive Summary & Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| :--- | :--- |")
    lines.append(f"| **Target Goal** | {target_title} |")
    lines.append(f"| **Total Certifications** | {len(roadmap_plan.all_certifications)} credentials |")
    lines.append(f"| **Total Study Hours** | {roadmap_plan.total_hours:,} hours |")
    lines.append(f"| **Estimated Timeline** | ~{roadmap_plan.total_weeks:.1f} weeks ({roadmap_plan.total_weeks / 4.33:.1f} months) @ {roadmap_plan.weekly_hours}h/wk |")
    lines.append(f"| **Total Exam Fees** | ${roadmap_plan.total_cost_usd:,.2f} USD |")
    lines.append(f"| **Unique Skills Gained** | {len(roadmap_plan.skills_progression)} competencies |")
    lines.append(f"| **Acquired Prereqs Held** | {len(roadmap_plan.current_certs)} certs |")
    lines.append("")

    # Budget Alert Callout
    if roadmap_plan.max_budget is not None:
        if roadmap_plan.budget_exceeded:
            lines.append(f"> [!WARNING]")
            lines.append(f"> **Budget Overrun Warning:** Total exam cost of **${roadmap_plan.total_cost_usd:,.2f} USD** exceeds your specified budget of **${roadmap_plan.max_budget:,.2f} USD** by **${abs(roadmap_plan.budget_remaining or 0):,.2f} USD**.")
            lines.append("")
        else:
            lines.append(f"> [!TIP]")
            lines.append(f"> **Budget Approved:** Total exam cost of **${roadmap_plan.total_cost_usd:,.2f} USD** is well within your budget limit of **${roadmap_plan.max_budget:,.2f} USD** (${roadmap_plan.budget_remaining:,.2f} remaining).")
            lines.append("")

    # Milestones & Checklist
    lines.append("## 🎯 Milestone Checklist & Timeline")
    lines.append("")
    lines.append("Track your incremental progress as you complete each credential on your path:")
    lines.append("")

    for m in roadmap_plan.milestones:
        code_str = f"`{m.exam_code}` " if m.exam_code else ""
        cost_str = f"${m.cost_usd:.0f}" if m.cost_usd > 0 else "Free"
        link_str = f"[{m.title}]({m.link})" if m.link else m.title
        lines.append(
            f"- [ ] **Milestone {m.index} (Target: Week {m.target_week:.1f})**: {link_str} {code_str}&mdash; *{m.provider} &bull; {m.level} &bull; {m.estimated_hours}h &bull; {cost_str}*"
        )
    lines.append("")

    # Phase Breakdown
    lines.append("## 📚 Multi-Stage Learning Journey")
    lines.append("")

    for p_idx, phase in enumerate(roadmap_plan.phases, start=1):
        lines.append(f"### {phase.phase_name}")
        lines.append(f"*{phase.description}*")
        lines.append("")
        lines.append(f"- **Phase Effort:** `{phase.estimated_hours} hours` (~`{phase.estimated_hours / roadmap_plan.weekly_hours:.1f} weeks`)")
        lines.append(f"- **Phase Exam Cost:** `${phase.cost_usd:,.2f} USD`")
        lines.append(f"- **Key Skills Added:** {', '.join(f'`{s}`' for s in phase.skills_gained[:8])}")
        lines.append("")

        # Certification table
        lines.append("| Credential | Provider | Level | Exam Code | Est. Hours | Exam Fee |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for cert in phase.certifications:
            t_link = f"[{cert.title}]({cert.link})" if cert.link else cert.title
            c_fee = f"${cert.cost_usd:,.2f}" if cert.cost_usd > 0 else "Free"
            code_txt = cert.exam_code or "—"
            lines.append(f"| **{t_link}** | {cert.provider} | `{cert.level}` | `{code_txt}` | {cert.estimated_hours}h | {c_fee} |")
        lines.append("")

        # Detailed cards with resources if requested
        if include_resources:
            for cert in phase.certifications:
                lines.append(f"#### 🎓 {cert.title} ({cert.provider})")
                lines.append(f"{cert.description}")
                lines.append("")
                if cert.skills_gained:
                    lines.append(f"- **Skills Mastered:** {', '.join(f'`{s}`' for s in cert.skills_gained)}")
                if cert.prerequisites:
                    lines.append(f"- **Prerequisites:** {', '.join(f'`{p}`' for p in cert.prerequisites)}")

                if cert.resources:
                    lines.append("- **Recommended Learning Resources:**")
                    for res in cert.resources:
                        lines.append(f"  - [{res.title}]({res.url}) *({res.type})*")
                lines.append("")

    # Skill Progression Matrix
    lines.append("## 🧠 Comprehensive Skill Progression")
    lines.append("")
    lines.append("By completing this sequenced certification journey, you will master the following technical competencies in order:")
    lines.append("")

    # Group skills into columns or list
    for idx, skill in enumerate(roadmap_plan.skills_progression, start=1):
        lines.append(f"{idx}. {skill}")
    lines.append("")

    # Study Methodology Tips
    lines.append("## 💡 Proven Exam Preparation Strategy")
    lines.append("")
    lines.append("1. **Active Recall & Hands-on Labs:** Complete practical labs and sandboxes rather than solely reading theory.")
    lines.append("2. **Practice Exams:** Consistently score 85%+ on timed full-length practice tests before booking the exam.")
    lines.append("3. **Community & Documentation:** Reference vendor documentation (AWS Whitepapers, Microsoft Learn, MDN, RFCs) to master edge cases.")
    lines.append("4. **Spaced Repetition:** Revisit flashcards for port numbers, CLI flags, and architectural limits every 48 hours.")
    lines.append("")

    return "\n".join(lines) + "\n"


def export_ascii_tree(
    target_id: str,
    catalog: Optional[CertificationCatalog] = None,
    dag_engine: Optional[DAGEngine] = None,
    show_dependents: bool = True,
) -> str:
    """Generate a clean ASCII box-drawing tree showing prerequisites and unlockable progressions."""
    cat = catalog if catalog is not None else CertificationCatalog()
    dag = dag_engine if dag_engine is not None else DAGEngine(cat)

    target_cert = cat.get_by_id(target_id)
    if not target_cert:
        return f"Certification ID '{target_id}' not found in catalog."

    lines: List[str] = []
    lines.append(f"================================================================================")
    cost_str = f"${target_cert.cost_usd:.0f}" if target_cert.cost_usd > 0 else "Free"
    lines.append(f"🎯 Target: [{target_cert.level}] {target_cert.title} ({target_cert.provider}) - {cost_str}, {target_cert.estimated_hours}h")
    lines.append(f"   ID: {target_cert.id} | Category: {target_cert.category} | Exam: {target_cert.exam_code or 'N/A'}")
    lines.append(f"================================================================================")
    lines.append("")

    # Section 1: Prerequisites Tree leading up to target
    prereqs = dag.resolve_prerequisites(target_id, include_target=False)
    lines.append("📚 Prerequisite Hierarchy (Earliest to Target):")

    if not prereqs:
        lines.append("   └── (None - Root entry point with no prerequisites)")
    else:
        # Build hierarchy tree upwards from target
        visited_nodes: Set[str] = set()

        def render_prereq_subtree(node_id: str, prefix: str = "", is_last: bool = True) -> None:
            c = cat.get_by_id(node_id)
            if not c:
                return
            branch = "└── " if is_last else "├── "
            c_cost = f"${c.cost_usd:.0f}" if c.cost_usd > 0 else "Free"
            lines.append(f"{prefix}{branch}[{c.level}] {c.title} ({c.provider}) - {c_cost}, {c.estimated_hours}h")

            if node_id in visited_nodes:
                return
            visited_nodes.add(node_id)

            parents = [p for p in c.prerequisites if cat.get_by_id(p)]
            new_prefix = prefix + ("    " if is_last else "│   ")
            for idx, p_id in enumerate(parents):
                render_prereq_subtree(p_id, new_prefix, is_last=(idx == len(parents) - 1))

        # Direct parents of target
        direct_prereqs = [p for p in target_cert.prerequisites if cat.get_by_id(p)]
        if direct_prereqs:
            for idx, p_id in enumerate(direct_prereqs):
                render_prereq_subtree(p_id, "   ", is_last=(idx == len(direct_prereqs) - 1))
        else:
            # If direct prerequisites list is empty but resolved prereqs exists
            for idx, p in enumerate(prereqs):
                p_cost = f"${p.cost_usd:.0f}" if p.cost_usd > 0 else "Free"
                branch = "└── " if idx == len(prereqs) - 1 else "├── "
                lines.append(f"   {branch}[{p.level}] {p.title} ({p.provider}) - {p_cost}, {p.estimated_hours}h")

    lines.append("")

    # Section 2: Unlocks & Next Steps
    if show_dependents:
        dependents = dag.resolve_dependents(target_id, include_self=False)
        lines.append("🔓 Unlocked Next Steps & Career Advancement:")
        if not dependents:
            lines.append("   └── (None - Capstone / Landmark certification)")
        else:
            visited_next: Set[str] = set()

            def render_next_subtree(node_id: str, prefix: str = "", is_last: bool = True) -> None:
                c = cat.get_by_id(node_id)
                if not c:
                    return
                branch = "└── " if is_last else "├── "
                c_cost = f"${c.cost_usd:.0f}" if c.cost_usd > 0 else "Free"
                lines.append(f"{prefix}{branch}[{c.level}] {c.title} ({c.provider}) - {c_cost}, {c.estimated_hours}h")

                if node_id in visited_next:
                    return
                visited_next.add(node_id)

                children = [n for n in c.next_steps if cat.get_by_id(n)]
                new_prefix = prefix + ("    " if is_last else "│   ")
                for idx, n_id in enumerate(children):
                    render_next_subtree(n_id, new_prefix, is_last=(idx == len(children) - 1))

            direct_next = [n for n in target_cert.next_steps if cat.get_by_id(n)]
            if direct_next:
                for idx, n_id in enumerate(direct_next):
                    render_next_subtree(n_id, "   ", is_last=(idx == len(direct_next) - 1))
            else:
                for idx, d in enumerate(dependents):
                    d_cost = f"${d.cost_usd:.0f}" if d.cost_usd > 0 else "Free"
                    branch = "└── " if idx == len(dependents) - 1 else "├── "
                    lines.append(f"   {branch}[{d.level}] {d.title} ({d.provider}) - {d_cost}, {d.estimated_hours}h")

    return "\n".join(lines) + "\n"


def export_json_ld(
    cert_or_roadmap: Union[Certification, RoadmapPlan],
    base_url: str = "https://certpath.dev",
    indent: int = 2,
) -> str:
    """Generate Schema.org EducationalOccupationalCredential or EducationalOccupationalProgram JSON-LD."""
    base_url = base_url.rstrip("/")

    if isinstance(cert_or_roadmap, Certification):
        cert = cert_or_roadmap
        data: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "EducationalOccupationalCredential",
            "@id": f"{base_url}/certs/{cert.id}",
            "name": cert.title,
            "description": cert.description,
            "credentialCategory": "certification",
            "educationalLevel": cert.level,
            "recognizedBy": {
                "@type": "Organization",
                "name": cert.provider,
            },
            "url": cert.link or f"{base_url}/certs/{cert.id}",
            "competencyRequired": cert.skills_gained,
            "timeRequired": f"PT{cert.estimated_hours}H",
            "offers": {
                "@type": "Offer",
                "price": cert.cost_usd,
                "priceCurrency": "USD",
            },
        }
        if cert.exam_code:
            data["identifier"] = cert.exam_code
        return json.dumps(data, indent=indent, ensure_ascii=False)

    elif isinstance(cert_or_roadmap, RoadmapPlan):
        plan = cert_or_roadmap
        items = []
        for idx, cert in enumerate(plan.all_certifications, start=1):
            items.append(
                {
                    "@type": "ListItem",
                    "position": idx,
                    "item": {
                        "@type": "EducationalOccupationalCredential",
                        "@id": f"{base_url}/certs/{cert.id}",
                        "name": cert.title,
                        "description": cert.description,
                        "educationalLevel": cert.level,
                        "recognizedBy": {
                            "@type": "Organization",
                            "name": cert.provider,
                        },
                        "url": cert.link or f"{base_url}/certs/{cert.id}",
                        "competencyRequired": cert.skills_gained,
                        "timeRequired": f"PT{cert.estimated_hours}H",
                        "offers": {
                            "@type": "Offer",
                            "price": cert.cost_usd,
                            "priceCurrency": "USD",
                        },
                    },
                }
            )

        data = {
            "@context": "https://schema.org",
            "@type": "EducationalOccupationalProgram",
            "@id": f"{base_url}/roadmaps/{_sanitize_mermaid_id(plan.target_name.lower())}",
            "name": f"Career Roadmap: {plan.target_name}",
            "description": f"Comprehensive progressive learning path comprising {len(plan.all_certifications)} industry certifications.",
            "timeToComplete": f"PT{plan.total_hours}H",
            "educationalCredentialAwarded": [f"{base_url}/certs/{c.id}" for c in plan.all_certifications],
            "occupationalCategory": plan.target_name,
            "hasCourse": {
                "@type": "ItemList",
                "numberOfItems": len(items),
                "itemListElement": items,
            },
        }
        return json.dumps(data, indent=indent, ensure_ascii=False)

    else:
        raise TypeError(f"Expected Certification or RoadmapPlan, got {type(cert_or_roadmap).__name__}")
