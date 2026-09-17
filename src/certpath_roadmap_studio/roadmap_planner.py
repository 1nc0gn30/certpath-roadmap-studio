"""Personalized career roadmap generator and skill gap analyzer for CertPath Roadmap Studio.

Transforms target certifications or career archetypes into multi-phase progressive learning plans
with milestone timelines, skill progression tracking, and budget/effort estimations.
Zero third-party dependencies (100% Python Standard Library).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Union

from .catalog import Certification, CertificationCatalog
from .dag_engine import DAGEngine


@dataclass
class CareerRole:
    """Predefined or custom career role archetype targeting a set of flagship certifications."""

    role_id: str
    title: str
    description: str
    category: str
    target_certs: List[str]
    key_skills: List[str] = field(default_factory=list)
    recommended_prereqs: List[str] = field(default_factory=list)
    target_level: str = "Advanced"

    def to_dict(self) -> Dict[str, Any]:
        """Convert career role to dictionary."""
        return {
            "role_id": self.role_id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "target_certs": list(self.target_certs),
            "key_skills": list(self.key_skills),
            "recommended_prereqs": list(self.recommended_prereqs),
            "target_level": self.target_level,
        }


# Industry-aligned built-in career role archetypes
BUILTIN_ROLES: Dict[str, CareerRole] = {
    "cloud_security_architect": CareerRole(
        role_id="cloud_security_architect",
        title="Cloud Security Architect",
        description="Designs, hardens, and audits multi-cloud zero-trust architectures, cloud-native security controls, and enterprise compliance posture.",
        category="Cloud Computing",
        target_certs=["cloud-azure-az500", "cyber-google-cloud-security", "cyber-ccsp", "cloud-aws-pro"],
        key_skills=["Cloud Security", "IAM", "Zero Trust", "KMS Encryption", "Multi-Cloud Governance", "Kubernetes Security"],
        target_level="Advanced",
    ),
    "ai_ml_engineer": CareerRole(
        role_id="ai_ml_engineer",
        title="AI & Machine Learning Engineer",
        description="Develops, trains, and productionizes deep learning models, LLM pipelines, and scalable cloud ML systems.",
        category="AI Development",
        target_certs=["ai-deep-learning", "ai-google-ml", "ai-aws-ml-specialty"],
        key_skills=["Machine Learning", "Deep Learning", "PyTorch/TensorFlow", "MLOps", "Model Optimization", "Feature Engineering"],
        target_level="Advanced",
    ),
    "fullstack_devops_lead": CareerRole(
        role_id="fullstack_devops_lead",
        title="Fullstack DevOps Lead",
        description="Leads modern web engineering and cloud infrastructure automation with containerization, CI/CD, and scalable full-stack architectures.",
        category="Software Development",
        target_certs=["web-fullstack-open", "cloud-cka", "cloud-terraform-associate"],
        key_skills=["React/Next.js", "Node.js/Python", "Kubernetes", "Infrastructure as Code", "Docker", "CI/CD Pipelines"],
        target_level="Advanced",
    ),
    "penetration_tester": CareerRole(
        role_id="penetration_tester",
        title="Offensive Security & Penetration Tester",
        description="Executes professional black-box/white-box penetration testing, vulnerability exploitation, web application assessments, and adversary simulation.",
        category="Cyber Security",
        target_certs=["cyber-oscp", "cyber-pentest-plus", "cyber-htb-cpst", "cyber-gpen"],
        key_skills=["Offensive Security", "Active Directory Exploitation", "Web Vulnerabilities", "Privilege Escalation", "Adversary Simulation"],
        target_level="Advanced",
    ),
    "data_platform_architect": CareerRole(
        role_id="data_platform_architect",
        title="Data Platform Architect",
        description="Architects high-throughput big data pipelines, lakehouses, real-time analytics platforms, and distributed cloud data warehouses.",
        category="Data Science",
        target_certs=["data-databricks-de", "data-gcp-data-engineer", "data-snowpro-core"],
        key_skills=["Apache Spark", "Data Lakehouse", "Snowflake", "dbt", "ETL/ELT Architecture", "Distributed Computing"],
        target_level="Advanced",
    ),
    "soc_analyst": CareerRole(
        role_id="soc_analyst",
        title="SOC Security Analyst & Incident Responder",
        description="Monitors security telemetry, executes proactive threat hunting, investigates SIEM alerts, and coordinates rapid incident containment.",
        category="Cyber Security",
        target_certs=["cyber-cysa-plus", "cyber-gcih", "cyber-cfr"],
        key_skills=["SIEM Monitoring", "Threat Hunting", "Incident Response", "Log Telemetry", "Forensics", "Behavioral Analytics"],
        target_level="Intermediate",
    ),
    "cloud_solutions_architect": CareerRole(
        role_id="cloud_solutions_architect",
        title="Enterprise Cloud Solutions Architect",
        description="Designs highly available, fault-tolerant, cost-optimized, and resilient enterprise cloud solutions across AWS and Azure.",
        category="Cloud Computing",
        target_certs=["cloud-aws-pro", "cloud-terraform-associate", "cloud-gcp-ace"],
        key_skills=["Cloud Architecture", "High Availability", "Terraform", "Cost Optimization", "Microservices", "Migration"],
        target_level="Advanced",
    ),
    "devops_platform_engineer": CareerRole(
        role_id="devops_platform_engineer",
        title="DevOps & Platform Engineer",
        description="Builds developer platforms, Kubernetes cluster orchestration, GitOps automation, and robust observability pipelines.",
        category="Cloud Computing",
        target_certs=["cloud-cka", "cloud-ckad", "cloud-terraform-associate"],
        key_skills=["Kubernetes", "GitOps", "Terraform", "Docker", "Prometheus/Grafana", "Linux Administration"],
        target_level="Advanced",
    ),
}


@dataclass
class RoadmapPhase:
    """Distinct learning stage within a multi-phase certification roadmap."""

    phase_name: str  # e.g., "Foundational", "Core Intermediate", "Advanced Specialization", "Capstone"
    description: str
    certifications: List[Certification] = field(default_factory=list)
    estimated_hours: int = 0
    cost_usd: float = 0.0
    skills_gained: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert phase to dictionary."""
        return {
            "phase_name": self.phase_name,
            "description": self.description,
            "certifications": [c.to_dict() for c in self.certifications],
            "estimated_hours": self.estimated_hours,
            "cost_usd": self.cost_usd,
            "skills_gained": list(self.skills_gained),
        }


@dataclass
class RoadmapMilestone:
    """Milestone marker on the certification journey."""

    index: int
    cert_id: str
    title: str
    provider: str
    phase_name: str
    level: str
    estimated_hours: int
    cumulative_hours: int
    target_week: float
    cost_usd: float
    skills_unlocked: List[str] = field(default_factory=list)
    exam_code: Optional[str] = None
    link: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert milestone to dictionary."""
        return {
            "index": self.index,
            "cert_id": self.cert_id,
            "title": self.title,
            "provider": self.provider,
            "phase_name": self.phase_name,
            "level": self.level,
            "estimated_hours": self.estimated_hours,
            "cumulative_hours": self.cumulative_hours,
            "target_week": self.target_week,
            "cost_usd": self.cost_usd,
            "skills_unlocked": list(self.skills_unlocked),
            "exam_code": self.exam_code,
            "link": self.link,
        }


@dataclass
class RoadmapPlan:
    """Comprehensive personalized certification roadmap plan."""

    target_name: str
    target_type: str  # "role" or "certification"
    target_role: Optional[CareerRole] = None
    target_cert: Optional[Certification] = None
    current_certs: List[str] = field(default_factory=list)
    phases: List[RoadmapPhase] = field(default_factory=list)
    all_certifications: List[Certification] = field(default_factory=list)
    total_hours: int = 0
    weekly_hours: int = 10
    total_weeks: float = 0.0
    total_cost_usd: float = 0.0
    skills_progression: List[str] = field(default_factory=list)
    milestones: List[RoadmapMilestone] = field(default_factory=list)
    budget_exceeded: bool = False
    budget_remaining: Optional[float] = None
    max_budget: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert entire roadmap plan to nested dictionary."""
        return {
            "target_name": self.target_name,
            "target_type": self.target_type,
            "target_role": self.target_role.to_dict() if self.target_role else None,
            "target_cert": self.target_cert.to_dict() if self.target_cert else None,
            "current_certs": list(self.current_certs),
            "phases": [p.to_dict() for p in self.phases],
            "all_certifications": [c.to_dict() for c in self.all_certifications],
            "total_hours": self.total_hours,
            "weekly_hours": self.weekly_hours,
            "total_weeks": self.total_weeks,
            "total_cost_usd": self.total_cost_usd,
            "skills_progression": list(self.skills_progression),
            "milestones": [m.to_dict() for m in self.milestones],
            "budget_exceeded": self.budget_exceeded,
            "budget_remaining": self.budget_remaining,
            "max_budget": self.max_budget,
        }


@dataclass
class SkillGapResult:
    """Analysis result comparing user skills against a target certification or role."""

    target_id: str
    target_title: str
    required_skills: List[str] = field(default_factory=list)
    acquired_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    match_percentage: float = 0.0
    recommended_certs: List[Certification] = field(default_factory=list)
    estimated_hours_to_bridge: int = 0
    estimated_cost_to_bridge: float = 0.0

    @property
    def target_skills(self) -> List[str]:
        """Alias for required_skills."""
        return self.required_skills

    def to_dict(self) -> Dict[str, Any]:
        """Convert skill gap result to dictionary."""
        return {
            "target_id": self.target_id,
            "target_title": self.target_title,
            "required_skills": list(self.required_skills),
            "acquired_skills": list(self.acquired_skills),
            "missing_skills": list(self.missing_skills),
            "match_percentage": self.match_percentage,
            "recommended_certs": [c.to_dict() for c in self.recommended_certs],
            "estimated_hours_to_bridge": self.estimated_hours_to_bridge,
            "estimated_cost_to_bridge": self.estimated_cost_to_bridge,
        }


class RoadmapPlanner:
    """Generates personalized multi-stage certification learning paths and career roadmaps."""

    def __init__(
        self,
        catalog: Optional[CertificationCatalog] = None,
        dag_engine: Optional[DAGEngine] = None,
    ) -> None:
        """Initialize planner with catalog and DAG engine."""
        self.catalog: CertificationCatalog = catalog if catalog is not None else CertificationCatalog()
        self.dag_engine: DAGEngine = dag_engine if dag_engine is not None else DAGEngine(self.catalog)
        self._roles: Dict[str, CareerRole] = dict(BUILTIN_ROLES)

    def register_role(self, role: CareerRole) -> None:
        """Register a custom career role archetype."""
        if not isinstance(role, CareerRole):
            raise TypeError(f"Expected CareerRole instance, got {type(role).__name__}")
        self._roles[role.role_id] = role

    def get_roles(self) -> List[CareerRole]:
        """Return all registered career roles."""
        return list(self._roles.values())

    def get_role(self, role_id: str) -> Optional[CareerRole]:
        """Look up a career role by ID."""
        return self._roles.get(str(role_id).strip())

    def generate_roadmap(
        self,
        target_role_or_cert: Union[str, CareerRole],
        current_certs: Optional[Sequence[str]] = None,
        weekly_hours: int = 10,
        max_budget: Optional[float] = None,
    ) -> RoadmapPlan:
        """Generate a personalized, topologically sequenced roadmap plan.

        Args:
            target_role_or_cert: Role ID (e.g. 'cloud_security_architect'),
                                 CareerRole instance, or Certification ID (e.g. 'cyber-cissp').
            current_certs: List of certification IDs the user already possesses.
            weekly_hours: Number of study hours available per week (default: 10).
            max_budget: Optional maximum exam budget limit in USD.
        """
        weekly_hours = max(1, int(weekly_hours))
        owned_cert_ids = set(str(c).strip() for c in (current_certs or []))

        # Determine target type and flagship certifications
        target_role: Optional[CareerRole] = None
        target_cert: Optional[Certification] = None
        flagship_cert_ids: List[str] = []
        target_name: str = ""
        target_type: str = "certification"

        if isinstance(target_role_or_cert, CareerRole):
            target_role = target_role_or_cert
            target_name = target_role.title
            target_type = "role"
            flagship_cert_ids = list(target_role.target_certs)
        elif isinstance(target_role_or_cert, str):
            role_lookup = self.get_role(target_role_or_cert)
            if role_lookup:
                target_role = role_lookup
                target_name = role_lookup.title
                target_type = "role"
                flagship_cert_ids = list(role_lookup.target_certs)
            else:
                cert_lookup = self.catalog.get_by_id(target_role_or_cert)
                if cert_lookup:
                    target_cert = cert_lookup
                    target_name = cert_lookup.title
                    target_type = "certification"
                    flagship_cert_ids = [cert_lookup.id]
                else:
                    # Treat string as target search or fallback cert ID
                    search_res = self.catalog.search(query=target_role_or_cert)
                    if search_res:
                        target_cert = search_res[0]
                        target_name = target_cert.title
                        target_type = "certification"
                        flagship_cert_ids = [target_cert.id]
                    else:
                        raise ValueError(f"Unknown career role or certification ID: '{target_role_or_cert}'")

        # Resolve all required prerequisite certifications across all flagship certs
        needed_ids: Set[str] = set()
        for cid in flagship_cert_ids:
            if cid in self.catalog:
                needed_ids.add(cid)
                prereqs = self.dag_engine.resolve_prerequisites(cid, include_target=False)
                for p in prereqs:
                    needed_ids.add(p.id)

        # Filter out certifications already owned
        unacquired_ids = needed_ids - owned_cert_ids

        # If user already possesses all needed certs
        if not unacquired_ids:
            return RoadmapPlan(
                target_name=target_name,
                target_type=target_type,
                target_role=target_role,
                target_cert=target_cert,
                current_certs=list(owned_cert_ids),
                phases=[],
                all_certifications=[],
                total_hours=0,
                weekly_hours=weekly_hours,
                total_weeks=0.0,
                total_cost_usd=0.0,
                skills_progression=[],
                milestones=[],
                budget_exceeded=False,
                budget_remaining=max_budget,
                max_budget=max_budget,
            )

        # Topologically sort the remaining unacquired certifications
        sequenced_certs = self.dag_engine._topological_sort_subset(unacquired_ids)

        # Partition into 4 structured phases:
        # 1. Foundational (Entry level / root prereqs)
        # 2. Core Intermediate (Intermediate level)
        # 3. Advanced Specialization (Advanced non-flagship / deep prereqs)
        # 4. Capstone (Flagship target certs)
        phase_1_certs: List[Certification] = []
        phase_2_certs: List[Certification] = []
        phase_3_certs: List[Certification] = []
        phase_4_certs: List[Certification] = []

        flagship_set = set(flagship_cert_ids)

        for cert in sequenced_certs:
            if cert.id in flagship_set and (len(flagship_set) == 1 or cert.level.lower() == "advanced"):
                phase_4_certs.append(cert)
            elif cert.level.lower() in ("entry", "foundational", "beginner"):
                phase_1_certs.append(cert)
            elif cert.level.lower() in ("intermediate", "associate"):
                phase_2_certs.append(cert)
            else:
                # Advanced or flagship
                if cert.id in flagship_set:
                    phase_4_certs.append(cert)
                else:
                    phase_3_certs.append(cert)

        # If phase 4 is empty, place the last cert(s) into Capstone
        if not phase_4_certs and sequenced_certs:
            if phase_3_certs:
                phase_4_certs.append(phase_3_certs.pop())
            elif phase_2_certs:
                phase_4_certs.append(phase_2_certs.pop())
            elif phase_1_certs:
                phase_4_certs.append(phase_1_certs.pop())

        raw_phases = [
            ("Phase 1: Foundational Fundamentals", "Master baseline core principles, terminology, and foundational concepts.", phase_1_certs),
            ("Phase 2: Core Intermediate Competencies", "Build hands-on operational capability, architectures, and intermediate workflows.", phase_2_certs),
            ("Phase 3: Advanced Specialization", "Deepen domain mastery with advanced architectures, threat mitigation, and production designs.", phase_3_certs),
            ("Phase 4: Capstone & Landmark Credentials", "Achieve flagship industry certifications verifying elite architectural mastery.", phase_4_certs),
        ]

        # Assemble structured RoadmapPhase instances
        phases: List[RoadmapPhase] = []
        for name, desc, p_certs in raw_phases:
            if p_certs:
                p_hours = sum(c.estimated_hours for c in p_certs)
                p_cost = sum(c.cost_usd for c in p_certs)
                p_skills: Set[str] = set()
                for c in p_certs:
                    p_skills.update(c.skills_gained)
                phases.append(
                    RoadmapPhase(
                        phase_name=name,
                        description=desc,
                        certifications=p_certs,
                        estimated_hours=p_hours,
                        cost_usd=round(p_cost, 2),
                        skills_gained=sorted(p_skills),
                    )
                )

        # Calculate totals
        total_hours = sum(c.estimated_hours for c in sequenced_certs)
        total_weeks = round(total_hours / float(weekly_hours), 1)
        total_cost = round(sum(c.cost_usd for c in sequenced_certs), 2)

        # Skills progression: ordered unique skills
        skills_progression: List[str] = []
        seen_skills: Set[str] = set()
        for c in sequenced_certs:
            for s in c.skills_gained:
                if s not in seen_skills:
                    seen_skills.add(s)
                    skills_progression.append(s)

        # Build milestones checklist
        milestones: List[RoadmapMilestone] = []
        cum_hours = 0
        m_idx = 1
        for phase in phases:
            for c in phase.certifications:
                cum_hours += c.estimated_hours
                target_wk = round(cum_hours / float(weekly_hours), 1)
                milestones.append(
                    RoadmapMilestone(
                        index=m_idx,
                        cert_id=c.id,
                        title=c.title,
                        provider=c.provider,
                        phase_name=phase.phase_name,
                        level=c.level,
                        estimated_hours=c.estimated_hours,
                        cumulative_hours=cum_hours,
                        target_week=target_wk,
                        cost_usd=c.cost_usd,
                        skills_unlocked=list(c.skills_gained),
                        exam_code=c.exam_code,
                        link=c.link,
                    )
                )
                m_idx += 1

        # Budget evaluation
        budget_exceeded = False
        budget_remaining: Optional[float] = None
        if max_budget is not None:
            budget_remaining = round(max_budget - total_cost, 2)
            budget_exceeded = total_cost > max_budget

        return RoadmapPlan(
            target_name=target_name,
            target_type=target_type,
            target_role=target_role,
            target_cert=target_cert,
            current_certs=list(owned_cert_ids),
            phases=phases,
            all_certifications=sequenced_certs,
            total_hours=total_hours,
            weekly_hours=weekly_hours,
            total_weeks=total_weeks,
            total_cost_usd=total_cost,
            skills_progression=skills_progression,
            milestones=milestones,
            budget_exceeded=budget_exceeded,
            budget_remaining=budget_remaining,
            max_budget=max_budget,
        )

    def skill_gap_analysis(
        self,
        target_role_or_cert: Union[str, CareerRole],
        acquired_skills: Optional[Sequence[str]] = None,
        current_certs: Optional[Sequence[str]] = None,
    ) -> SkillGapResult:
        """Perform a skill gap analysis comparing possessed skills against a target role/cert."""
        # Resolve target certifications
        target_certs: List[Certification] = []
        target_id: str = ""
        target_title: str = ""

        if isinstance(target_role_or_cert, CareerRole):
            target_id = target_role_or_cert.role_id
            target_title = target_role_or_cert.title
            target_certs = [self.catalog.get_by_id(cid) for cid in target_role_or_cert.target_certs if self.catalog.get_by_id(cid)]
        elif isinstance(target_role_or_cert, str):
            role_lookup = self.get_role(target_role_or_cert)
            if role_lookup:
                target_id = role_lookup.role_id
                target_title = role_lookup.title
                target_certs = [self.catalog.get_by_id(cid) for cid in role_lookup.target_certs if self.catalog.get_by_id(cid)]
            else:
                cert_lookup = self.catalog.get_by_id(target_role_or_cert)
                if cert_lookup:
                    target_id = cert_lookup.id
                    target_title = cert_lookup.title
                    target_certs = [cert_lookup]
                else:
                    raise ValueError(f"Unknown career role or certification: '{target_role_or_cert}'")

        # Collect required skills across target and prerequisite graph
        req_skills_set: Set[str] = set()
        for tc in target_certs:
            req_skills_set.update(tc.skills_gained)
            prereqs = self.dag_engine.resolve_prerequisites(tc.id, include_target=False)
            for p in prereqs:
                req_skills_set.update(p.skills_gained)

        # Collect user's acquired skills
        user_skills_set: Set[str] = set(s.strip() for s in (acquired_skills or []) if s.strip())
        for cid in (current_certs or []):
            cert = self.catalog.get_by_id(cid)
            if cert:
                user_skills_set.update(cert.skills_gained)

        user_skills_lower = {s.lower() for s in user_skills_set}
        required_skills = sorted(req_skills_set)
        missing_skills: List[str] = []

        for req in required_skills:
            if req.lower() not in user_skills_lower:
                missing_skills.append(req)

        # Match percentage
        total_req = len(required_skills)
        if total_req > 0:
            matched_count = total_req - len(missing_skills)
            match_pct = round(100.0 * matched_count / float(total_req), 1)
        else:
            match_pct = 100.0

        # Generate roadmap of certifications needed to bridge the gap
        roadmap = self.generate_roadmap(
            target_role_or_cert=target_role_or_cert,
            current_certs=current_certs,
        )

        return SkillGapResult(
            target_id=target_id,
            target_title=target_title,
            required_skills=required_skills,
            acquired_skills=sorted(user_skills_set),
            missing_skills=missing_skills,
            match_percentage=match_pct,
            recommended_certs=roadmap.all_certifications,
            estimated_hours_to_bridge=roadmap.total_hours,
            estimated_cost_to_bridge=roadmap.total_cost_usd,
        )
