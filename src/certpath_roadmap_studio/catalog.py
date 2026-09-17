"""Certification catalog models and repository for CertPath Roadmap Studio.

Defines rich certification metadata dataclasses, serialization logic,
multi-criteria search and filtering, and statistical summaries.
Zero third-party dependencies (100% Python Standard Library).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Union

from .compat import normalize_path, read_json_safe

# Common known exam codes for automatic detection when missing from JSON
KNOWN_EXAM_PATTERNS = [
    re.compile(r"\b(AZ-[0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\b(AI-[0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\b(DP-[0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\b(SC-[0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\b(MS-[0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\b(PL-[0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\b(CLF-C0[1-9])\b", re.IGNORECASE),
    re.compile(r"\b(SAA-C0[1-9])\b", re.IGNORECASE),
    re.compile(r"\b(DVA-C0[1-9])\b", re.IGNORECASE),
    re.compile(r"\b(SOA-C0[1-9])\b", re.IGNORECASE),
    re.compile(r"\b(SAP-C0[1-9])\b", re.IGNORECASE),
    re.compile(r"\b(DOP-C0[1-9])\b", re.IGNORECASE),
    re.compile(r"\b(SCS-C0[1-9])\b", re.IGNORECASE),
    re.compile(r"\b(MLS-C0[1-9])\b", re.IGNORECASE),
    re.compile(r"\b(ANS-C0[1-9])\b", re.IGNORECASE),
    re.compile(r"\b(DAS-C0[1-9])\b", re.IGNORECASE),
    re.compile(r"\b(SY0-[0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\b(N10-[0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\b(220-[0-9]{4})\b", re.IGNORECASE),
    re.compile(r"\b(CS0-[0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\b(PT0-[0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\b(CAS-[0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\b(XK0-[0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\b(200-301|350-401|350-701|350-201)\b", re.IGNORECASE),
    re.compile(r"\b(CKA|CKAD|CKS|LFCS|LFCE)\b", re.IGNORECASE),
    re.compile(r"\b(CISSP|CCSP|SSCP|CC|CISM|CISA|CRISC)\b", re.IGNORECASE),
    re.compile(r"\b(OSCP|OSWE|OSEP|OSED|OSMR)\b", re.IGNORECASE),
]


def _infer_exam_code(cert_id: str, title: str, description: str) -> Optional[str]:
    """Attempt to detect recognized exam codes from cert identifiers or text."""
    combined = f"{cert_id} {title} {description}"
    for pat in KNOWN_EXAM_PATTERNS:
        match = pat.search(combined)
        if match:
            return match.group(1).upper()
    return None


def _infer_estimated_hours(level: str, cert_id: str = "") -> int:
    """Infer realistic estimated study hours if not provided."""
    lvl = level.lower().strip()
    if "entry" in lvl or "foundational" in lvl or "beginner" in lvl:
        return 40
    elif "intermediate" in lvl or "associate" in lvl:
        return 80
    elif "advanced" in lvl or "expert" in lvl or "specialty" in lvl or "professional" in lvl:
        return 140
    return 60


def _infer_cost_usd(provider: str, level: str, title: str) -> float:
    """Infer realistic official exam fee based on provider and level."""
    prov = provider.lower()
    lvl = level.lower()
    t = title.lower()

    if "freecodecamp" in prov or "the odin project" in prov or "kaggle" in prov:
        return 0.0
    if "aws" in prov or "amazon" in prov:
        if "foundational" in lvl or "practitioner" in t:
            return 100.0
        if "associate" in lvl or "associate" in t:
            return 150.0
        return 300.0
    if "microsoft" in prov or "azure" in prov:
        if "fundamentals" in t or "entry" in lvl:
            return 99.0
        return 165.0
    if "google" in prov or "gcp" in prov:
        if "digital leader" in t:
            return 99.0
        if "associate" in t or "entry" in lvl:
            return 125.0
        return 200.0
    if "comptia" in prov:
        if "a+" in t:
            return 246.0
        if "security+" in t or "cysa+" in t or "pentest+" in t:
            return 392.0
        if "casp" in t or "securityx" in t:
            return 494.0
        return 358.0
    if "cisco" in prov:
        if "ccna" in t or "cyberops" in t:
            return 300.0
        if "ccnp" in t:
            return 400.0
        return 300.0
    if "isc" in prov:
        if "certified in cybersecurity" in t or "cc" == t:
            return 50.0
        if "cissp" in t:
            return 749.0
        if "ccsp" in t:
            return 599.0
        return 249.0
    if "linux foundation" in prov:
        return 395.0
    if "hashicorp" in prov:
        return 70.5
    if "offensive security" in prov or "offsec" in prov:
        return 1649.0

    # Default heuristic by level
    if "entry" in lvl:
        return 50.0
    if "intermediate" in lvl:
        return 150.0
    if "advanced" in lvl:
        return 300.0
    return 100.0


@dataclass
class CertificationResource:
    """Learning resource (official guide, course, practice lab, or book)."""

    title: str
    url: str
    type: str = "Official"  # Official, Course, Practice, Book, Documentation

    def to_dict(self) -> Dict[str, Any]:
        """Convert resource to dictionary."""
        return {
            "title": self.title,
            "url": self.url,
            "type": self.type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CertificationResource:
        """Construct from raw dictionary."""
        return cls(
            title=str(data.get("title", "Resource")),
            url=str(data.get("url", "")),
            type=str(data.get("type", "Official")),
        )


@dataclass
class Certification:
    """Comprehensive certification entity including prerequisites, skills, and metadata."""

    id: str
    title: str
    provider: str
    level: str  # Entry, Intermediate, Advanced
    category: str
    description: str
    skills_gained: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    link: str = ""
    color: str = "#3b82f6"
    next_steps: List[str] = field(default_factory=list)
    resources: List[CertificationResource] = field(default_factory=list)
    interests: List[str] = field(default_factory=list)
    estimated_hours: int = 40
    cost_usd: float = 0.0
    exam_code: Optional[str] = None

    def __post_init__(self) -> None:
        """Normalize types and enforce clean defaults."""
        self.id = str(self.id).strip()
        self.title = str(self.title).strip()
        self.provider = str(self.provider).strip()
        self.level = str(self.level).strip()
        self.category = str(self.category).strip()
        self.description = str(self.description).strip()
        self.link = str(self.link).strip()
        self.color = str(self.color).strip() or "#3b82f6"

        # Ensure lists
        self.skills_gained = [str(s).strip() for s in self.skills_gained if str(s).strip()]
        self.prerequisites = [str(p).strip() for p in self.prerequisites if str(p).strip()]
        self.next_steps = [str(n).strip() for n in self.next_steps if str(n).strip()]
        self.interests = [str(i).strip() for i in self.interests if str(i).strip()]

        # Ensure resource dataclass instances
        res_list: List[CertificationResource] = []
        for r in self.resources:
            if isinstance(r, CertificationResource):
                res_list.append(r)
            elif isinstance(r, dict):
                res_list.append(CertificationResource.from_dict(r))
        self.resources = res_list

        self.estimated_hours = int(self.estimated_hours) if self.estimated_hours > 0 else 40
        self.cost_usd = float(self.cost_usd) if self.cost_usd >= 0.0 else 0.0

        if not self.exam_code:
            self.exam_code = _infer_exam_code(self.id, self.title, self.description)

    def to_dict(self, camel_case: bool = False) -> Dict[str, Any]:
        """Convert certification to dictionary with snake_case or camelCase keys."""
        res_dicts = [r.to_dict() for r in self.resources]
        if camel_case:
            return {
                "id": self.id,
                "title": self.title,
                "provider": self.provider,
                "level": self.level,
                "category": self.category,
                "description": self.description,
                "skillsGained": list(self.skills_gained),
                "prerequisites": list(self.prerequisites),
                "link": self.link,
                "color": self.color,
                "nextSteps": list(self.next_steps),
                "resources": res_dicts,
                "interests": list(self.interests),
                "estimatedHours": self.estimated_hours,
                "costUsd": self.cost_usd,
                "examCode": self.exam_code,
            }
        return {
            "id": self.id,
            "title": self.title,
            "provider": self.provider,
            "level": self.level,
            "category": self.category,
            "description": self.description,
            "skills_gained": list(self.skills_gained),
            "prerequisites": list(self.prerequisites),
            "link": self.link,
            "color": self.color,
            "next_steps": list(self.next_steps),
            "resources": res_dicts,
            "interests": list(self.interests),
            "estimated_hours": self.estimated_hours,
            "cost_usd": self.cost_usd,
            "exam_code": self.exam_code,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Certification:
        """Construct a Certification instance from dictionary supporting both camelCase and snake_case."""
        cert_id = str(data.get("id", ""))
        title = str(data.get("title", ""))
        provider = str(data.get("provider", "Independent"))
        level = str(data.get("level", "Intermediate"))
        category = str(data.get("category", "General"))
        description = str(data.get("description", ""))
        link = str(data.get("link", ""))
        color = str(data.get("color", "#3b82f6"))

        # Keys in camelCase or snake_case
        skills = data.get("skills_gained") or data.get("skillsGained") or []
        prereqs = data.get("prerequisites") or []
        next_steps = data.get("next_steps") or data.get("nextSteps") or []
        interests = data.get("interests") or []
        resources_raw = data.get("resources") or []

        # Exam code
        exam_code = data.get("exam_code") or data.get("examCode")
        if not exam_code:
            exam_code = _infer_exam_code(cert_id, title, description)

        # Estimated hours
        raw_hours = data.get("estimated_hours") or data.get("estimatedHours")
        if raw_hours is not None:
            hours = int(raw_hours)
        else:
            hours = _infer_estimated_hours(level, cert_id)

        # Cost
        raw_cost = data.get("cost_usd") or data.get("costUsd")
        if raw_cost is not None:
            cost = float(raw_cost)
        else:
            cost = _infer_cost_usd(provider, level, title)

        resources: List[CertificationResource] = []
        for r in resources_raw:
            if isinstance(r, dict):
                resources.append(CertificationResource.from_dict(r))
            elif isinstance(r, CertificationResource):
                resources.append(r)

        return cls(
            id=cert_id,
            title=title,
            provider=provider,
            level=level,
            category=category,
            description=description,
            skills_gained=list(skills),
            prerequisites=list(prereqs),
            link=link,
            color=color,
            next_steps=list(next_steps),
            resources=resources,
            interests=list(interests),
            estimated_hours=hours,
            cost_usd=cost,
            exam_code=exam_code,
        )


# Minimal built-in fallback dataset to guarantee standalone functionality
FALLBACK_CERTIFICATIONS_DATA: List[Dict[str, Any]] = [
    {
        "id": "comptia-itf",
        "title": "CompTIA IT Fundamentals+ (ITF+)",
        "provider": "CompTIA",
        "level": "Entry",
        "category": "IT Management & Support",
        "description": "Foundational introduction to basic computer hardware, networking, and security.",
        "skillsGained": ["Hardware Basics", "Networking Fundamentals", "Security Concepts", "Troubleshooting"],
        "prerequisites": [],
        "link": "https://www.comptia.org/certifications/it-fundamentals",
        "color": "#ef4444",
        "nextSteps": ["comptia-a-plus"],
        "interests": ["it", "hardware", "support"],
        "resources": [{"title": "Official Exam Objectives", "url": "https://www.comptia.org", "type": "Official"}],
    },
    {
        "id": "comptia-a-plus",
        "title": "CompTIA A+",
        "provider": "CompTIA",
        "level": "Entry",
        "category": "IT Management & Support",
        "description": "The industry standard for launching IT support and infrastructure careers.",
        "skillsGained": ["Operating Systems", "Hardware", "Virtualization", "Cloud Basics", "Troubleshooting"],
        "prerequisites": ["comptia-itf"],
        "link": "https://www.comptia.org/certifications/a",
        "color": "#f97316",
        "nextSteps": ["comptia-network-plus", "comptia-security-plus"],
        "interests": ["it", "hardware", "support", "helpdesk"],
        "resources": [{"title": "CompTIA A+ Guide", "url": "https://www.comptia.org", "type": "Official"}],
    },
    {
        "id": "comptia-network-plus",
        "title": "CompTIA Network+",
        "provider": "CompTIA",
        "level": "Intermediate",
        "category": "IT Management & Support",
        "description": "Essential network architecture, protocols, topologies, and routing fundamentals.",
        "skillsGained": ["TCP/IP", "Subnetting", "Routing & Switching", "Network Security", "DNS/DHCP"],
        "prerequisites": ["comptia-a-plus"],
        "link": "https://www.comptia.org/certifications/network",
        "color": "#3b82f6",
        "nextSteps": ["comptia-security-plus", "cisco-ccna"],
        "interests": ["networking", "infrastructure", "telecom"],
        "resources": [{"title": "CompTIA Network+ Hub", "url": "https://www.comptia.org", "type": "Official"}],
    },
    {
        "id": "comptia-security-plus",
        "title": "CompTIA Security+",
        "provider": "CompTIA",
        "level": "Intermediate",
        "category": "Cyber Security",
        "description": "Baseline cybersecurity certification covering threat analysis, cryptography, and defense.",
        "skillsGained": ["Threat Analysis", "Cryptography", "Identity & Access Management", "Vulnerability Assessment"],
        "prerequisites": ["comptia-network-plus"],
        "link": "https://www.comptia.org/certifications/security",
        "color": "#dc2626",
        "nextSteps": ["comptia-cysa-plus", "comptia-pentest-plus", "aws-security-specialty"],
        "interests": ["security", "infosec", "cyber", "defense"],
        "resources": [{"title": "CompTIA Security+ Study Guide", "url": "https://www.comptia.org", "type": "Official"}],
    },
    {
        "id": "comptia-cysa-plus",
        "title": "CompTIA CySA+ (Cybersecurity Analyst)",
        "provider": "CompTIA",
        "level": "Advanced",
        "category": "Cyber Security",
        "description": "Behavioral analytics and threat intelligence for security operations center (SOC) analysts.",
        "skillsGained": ["Threat Hunting", "SIEM Monitoring", "Incident Response", "Vulnerability Management"],
        "prerequisites": ["comptia-security-plus"],
        "link": "https://www.comptia.org/certifications/cybersecurity-analyst",
        "color": "#b91c1c",
        "nextSteps": ["isc2-cissp"],
        "interests": ["soc", "threat-hunting", "incident-response"],
        "resources": [{"title": "CySA+ Learning Materials", "url": "https://www.comptia.org", "type": "Official"}],
    },
    {
        "id": "aws-cloud-practitioner",
        "title": "AWS Certified Cloud Practitioner",
        "provider": "AWS",
        "level": "Entry",
        "category": "Cloud Computing",
        "description": "Fundamental high-level understanding of AWS Cloud concepts, services, and security.",
        "skillsGained": ["AWS Core Services", "Cloud Architecture", "Cloud Billing & Pricing", "Shared Responsibility Model"],
        "prerequisites": [],
        "link": "https://aws.amazon.com/certification/certified-cloud-practitioner/",
        "color": "#f59e0b",
        "nextSteps": ["aws-solutions-architect-associate", "aws-developer-associate"],
        "interests": ["cloud", "aws", "architecture"],
        "resources": [{"title": "AWS Skill Builder", "url": "https://skillbuilder.aws", "type": "Official"}],
    },
    {
        "id": "aws-solutions-architect-associate",
        "title": "AWS Certified Solutions Architect – Associate",
        "provider": "AWS",
        "level": "Intermediate",
        "category": "Cloud Computing",
        "description": "Design resilient, high-performing, secure, and cost-optimized architectures on AWS.",
        "skillsGained": ["AWS VPC & Networking", "EC2 & S3", "High Availability & Auto-scaling", "IAM & S3 Security"],
        "prerequisites": ["aws-cloud-practitioner"],
        "link": "https://aws.amazon.com/certification/certified-solutions-architect-associate/",
        "color": "#eab308",
        "nextSteps": ["aws-solutions-architect-professional", "aws-security-specialty"],
        "interests": ["cloud", "architecture", "aws", "infrastructure"],
        "resources": [{"title": "AWS Ramp-Up Guide: Architect", "url": "https://aws.amazon.com", "type": "Official"}],
    },
    {
        "id": "aws-security-specialty",
        "title": "AWS Certified Security – Specialty",
        "provider": "AWS",
        "level": "Advanced",
        "category": "Cyber Security",
        "description": "Master AWS security controls, encryption, incident response, and compliance auditing.",
        "skillsGained": ["KMS & Encryption", "IAM Policies & Governance", "GuardDuty & Security Hub", "VPC Security & WAF"],
        "prerequisites": ["aws-solutions-architect-associate", "comptia-security-plus"],
        "link": "https://aws.amazon.com/certification/certified-security-specialty/",
        "color": "#ef4444",
        "nextSteps": ["isc2-cissp"],
        "interests": ["cloud-security", "aws", "infosec", "encryption"],
        "resources": [{"title": "AWS Security Specialty Path", "url": "https://aws.amazon.com", "type": "Official"}],
    },
    {
        "id": "isc2-cissp",
        "title": "ISC2 CISSP (Certified Information Systems Security Professional)",
        "provider": "ISC2",
        "level": "Advanced",
        "category": "Cyber Security",
        "description": "The gold standard executive & architectural certification in enterprise information security.",
        "skillsGained": ["Security Governance & Risk", "Asset Security", "Security Architecture", "Network Security", "IAM", "Security Operations"],
        "prerequisites": ["comptia-cysa-plus", "aws-security-specialty"],
        "link": "https://www.isc2.org/certifications/cissp",
        "color": "#991b1b",
        "nextSteps": [],
        "interests": ["security", "executive", "governance", "architecture"],
        "resources": [{"title": "ISC2 CISSP Exam Outline", "url": "https://www.isc2.org", "type": "Official"}],
    },
    {
        "id": "web-html-css",
        "title": "Responsive Web Design",
        "provider": "freeCodeCamp",
        "level": "Entry",
        "category": "Web Development",
        "description": "Build accessible, responsive sites with modern HTML5, CSS3, Flexbox, and CSS Grid.",
        "skillsGained": ["HTML5", "CSS3", "Flexbox", "CSS Grid", "Responsive Design", "Accessibility"],
        "prerequisites": [],
        "link": "https://www.freecodecamp.org/learn/2022/responsive-web-design/",
        "color": "#10b981",
        "nextSteps": ["web-js-algorithms"],
        "interests": ["web", "frontend", "design", "ui"],
        "resources": [{"title": "freeCodeCamp Curriculum", "url": "https://www.freecodecamp.org", "type": "Official"}],
    },
    {
        "id": "web-js-algorithms",
        "title": "JavaScript Algorithms and Data Structures",
        "provider": "freeCodeCamp",
        "level": "Entry",
        "category": "Web Development",
        "description": "Develop core modern JavaScript syntax, ES6, OOP, functional programming, and algorithms.",
        "skillsGained": ["JavaScript", "ES6+", "Data Structures", "Algorithms", "DOM Manipulation"],
        "prerequisites": ["web-html-css"],
        "link": "https://www.freecodecamp.org/learn/javascript-algorithms-and-data-structures-v8/",
        "color": "#f59e0b",
        "nextSteps": ["web-fcc-frontend"],
        "interests": ["javascript", "coding", "frontend", "algorithms"],
        "resources": [{"title": "JavaScript Guide MDN", "url": "https://developer.mozilla.org", "type": "Documentation"}],
    },
    {
        "id": "web-fcc-frontend",
        "title": "Front End Development Libraries",
        "provider": "freeCodeCamp",
        "level": "Intermediate",
        "category": "Web Development",
        "description": "Ship modern single-page applications with React, Redux, Sass, and Bootstrap.",
        "skillsGained": ["React", "Redux", "Component State", "Hooks", "Sass", "Bootstrap"],
        "prerequisites": ["web-js-algorithms"],
        "link": "https://www.freecodecamp.org/learn/front-end-development-libraries/",
        "color": "#06b6d4",
        "nextSteps": [],
        "interests": ["react", "frontend", "spa", "ui"],
        "resources": [{"title": "React Docs", "url": "https://react.dev", "type": "Official"}],
    },
]


class CertificationCatalog:
    """In-memory searchable and filterable catalog of IT, Cloud, and Developer certifications."""

    def __init__(
        self,
        certs_file: Optional[Union[str, Path]] = None,
        data_path: Optional[Union[str, Path]] = None,
        auto_load: bool = True,
    ) -> None:
        """Initialize catalog.

        If `certs_file` or `data_path` is provided, loads from file. Otherwise checks default paths
        or uses built-in fallback data.
        """
        self._certs: Dict[str, Certification] = {}
        target_file = certs_file or data_path
        if auto_load:
            self._load_initial_data(target_file)

    def _find_default_certs_file(self) -> Optional[Path]:
        """Locate certs.json in standard package or workspace paths."""
        current_dir = Path(__file__).resolve().parent
        candidate_paths = [
            current_dir / "data" / "certs.json",
            current_dir.parent.parent / "src" / "certpath_roadmap_studio" / "data" / "certs.json",
            current_dir.parent.parent / "public" / "certs.json",
            Path.cwd() / "src" / "certpath_roadmap_studio" / "data" / "certs.json",
            Path.cwd() / "public" / "certs.json",
        ]
        for p in candidate_paths:
            if p.exists() and p.is_file():
                return p
        return None

    def _load_initial_data(self, certs_file: Optional[Union[str, Path]]) -> None:
        """Load data from file or fallback dataset."""
        if certs_file:
            path = normalize_path(certs_file)
            if path.exists() and path.is_file():
                self.load_from_file(path)
                return

        default_path = self._find_default_certs_file()
        if default_path and default_path.exists():
            self.load_from_file(default_path)
        else:
            self.load_from_list(FALLBACK_CERTIFICATIONS_DATA)

    def load_from_file(self, path: Union[str, Path]) -> int:
        """Load certifications from JSON file. Returns count of loaded certs."""
        data = read_json_safe(path, default=[])
        if not isinstance(data, list):
            raise ValueError(f"Expected JSON array in {path}, got {type(data).__name__}")
        return self.load_from_list(data)

    def load_from_list(self, cert_dicts: Sequence[Dict[str, Any]]) -> int:
        """Load certifications from list of dictionaries. Returns count loaded."""
        loaded_count = 0
        for item in cert_dicts:
            if isinstance(item, dict):
                cert = Certification.from_dict(item)
                if cert.id:
                    self._certs[cert.id] = cert
                    loaded_count += 1
        return loaded_count

    def add_certification(self, cert: Certification, overwrite: bool = True) -> None:
        """Add or update a certification in the catalog."""
        if not isinstance(cert, Certification):
            raise TypeError(f"Expected Certification instance, got {type(cert).__name__}")
        if not cert.id:
            raise ValueError("Certification ID cannot be empty")
        if cert.id in self._certs and not overwrite:
            raise KeyError(f"Certification ID '{cert.id}' already exists")
        self._certs[cert.id] = cert

    def remove_certification(self, cert_id: str) -> bool:
        """Remove a certification by ID. Returns True if removed, False if not found."""
        if cert_id in self._certs:
            del self._certs[cert_id]
            return True
        return False

    def get_by_id(self, cert_id: str) -> Optional[Certification]:
        """Look up certification by unique ID."""
        return self._certs.get(str(cert_id).strip())

    def get_all(self) -> List[Certification]:
        """Return all certifications in catalog."""
        return list(self._certs.values())

    def __len__(self) -> int:
        return len(self._certs)

    def __iter__(self):
        return iter(self._certs.values())

    def __contains__(self, cert_id: str) -> bool:
        return cert_id in self._certs

    def get_categories(self) -> List[str]:
        """Return sorted unique list of all certification categories."""
        categories = {c.category for c in self._certs.values() if c.category}
        return sorted(categories)

    def get_providers(self) -> List[str]:
        """Return sorted unique list of all certification providers."""
        providers = {c.provider for c in self._certs.values() if c.provider}
        return sorted(providers)

    def get_levels(self) -> List[str]:
        """Return sorted list of certification levels."""
        order = {"entry": 0, "foundational": 0, "intermediate": 1, "associate": 1, "advanced": 2, "expert": 2}
        levels = {c.level for c in self._certs.values() if c.level}
        return sorted(levels, key=lambda lvl: (order.get(lvl.lower(), 99), lvl))

    def get_all_skills(self) -> List[str]:
        """Return sorted unique list of all skills gained across all certifications."""
        skills: Set[str] = set()
        for c in self._certs.values():
            skills.update(c.skills_gained)
        return sorted(skills)

    def get_all_interests(self) -> List[str]:
        """Return sorted unique list of all interest tags."""
        interests: Set[str] = set()
        for c in self._certs.values():
            interests.update(c.interests)
        return sorted(interests)

    def search(
        self,
        query: Optional[str] = None,
        provider: Optional[str] = None,
        level: Optional[str] = None,
        category: Optional[str] = None,
        skill: Optional[str] = None,
        interest: Optional[str] = None,
        max_cost: Optional[float] = None,
        max_hours: Optional[int] = None,
    ) -> List[Certification]:
        """Search and filter certifications with multi-criteria AND logic."""
        results: List[Certification] = []
        q = query.lower().strip() if query else None
        p_filter = provider.lower().strip() if provider else None
        l_filter = level.lower().strip() if level else None
        c_filter = category.lower().strip() if category else None
        s_filter = skill.lower().strip() if skill else None
        i_filter = interest.lower().strip() if interest else None

        for cert in self._certs.values():
            # Provider filter
            if p_filter and cert.provider.lower() != p_filter:
                if p_filter not in cert.provider.lower():
                    continue

            # Level filter
            if l_filter and cert.level.lower() != l_filter:
                if l_filter not in cert.level.lower():
                    continue

            # Category filter
            if c_filter and cert.category.lower() != c_filter:
                if c_filter not in cert.category.lower():
                    continue

            # Skill filter
            if s_filter:
                cert_skills_lower = [s.lower() for s in cert.skills_gained]
                if not any(s_filter in sk for sk in cert_skills_lower):
                    continue

            # Interest filter
            if i_filter:
                cert_interests_lower = [i.lower() for i in cert.interests]
                if not any(i_filter in it for it in cert_interests_lower):
                    continue

            # Max cost filter
            if max_cost is not None and cert.cost_usd > max_cost:
                continue

            # Max hours filter
            if max_hours is not None and cert.estimated_hours > max_hours:
                continue

            # Free-form search query
            if q:
                searchable_text = (
                    f"{cert.id} {cert.title} {cert.provider} {cert.category} "
                    f"{cert.description} {cert.exam_code or ''} "
                    f"{' '.join(cert.skills_gained)} {' '.join(cert.interests)}"
                ).lower()
                if q not in searchable_text:
                    continue

            results.append(cert)

        return results

    @property
    def total_certs(self) -> int:
        """Total number of certifications."""
        return len(self._certs)

    @property
    def by_category(self) -> Dict[str, int]:
        """Count of certifications grouped by category."""
        counts: Dict[str, int] = {}
        for c in self._certs.values():
            counts[c.category] = counts.get(c.category, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))

    @property
    def by_provider(self) -> Dict[str, int]:
        """Count of certifications grouped by provider."""
        counts: Dict[str, int] = {}
        for c in self._certs.values():
            counts[c.provider] = counts.get(c.provider, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))

    @property
    def by_level(self) -> Dict[str, int]:
        """Count of certifications grouped by level."""
        counts: Dict[str, int] = {}
        for c in self._certs.values():
            counts[c.level] = counts.get(c.level, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))

    def summary_statistics(self) -> Dict[str, Any]:
        """Compute aggregated statistics across the entire catalog."""
        total = len(self._certs)
        if total == 0:
            return {
                "total_certs": 0,
                "by_category": {},
                "by_provider": {},
                "by_level": {},
                "total_skills": 0,
                "average_hours": 0.0,
                "average_cost": 0.0,
                "free_certs_count": 0,
            }

        total_hours = sum(c.estimated_hours for c in self._certs.values())
        total_cost = sum(c.cost_usd for c in self._certs.values())
        free_certs = sum(1 for c in self._certs.values() if c.cost_usd == 0.0)
        skills = self.get_all_skills()

        return {
            "total_certs": total,
            "by_category": self.by_category,
            "by_provider": self.by_provider,
            "by_level": self.by_level,
            "total_skills": len(skills),
            "average_hours": round(total_hours / total, 1),
            "average_cost": round(total_cost / total, 2),
            "free_certs_count": free_certs,
        }
