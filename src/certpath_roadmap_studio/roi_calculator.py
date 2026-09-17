"""Certification ROI, Compensation Impact, and Skill Overlap Matrix Engine.

Analyzes financial return on investment, exam payback horizons, study-hour
synergies between overlapping credentials, and credential portfolio valuation.
Zero third-party runtime dependencies (100% Python Standard Library).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from .catalog import Certification, CertificationCatalog


# Baseline salary premium heuristics by level and category (annual USD)
BASE_SALARY_PREMIUM = {
    "entry": 4500.0,
    "foundational": 4000.0,
    "intermediate": 9500.0,
    "associate": 9000.0,
    "advanced": 18000.0,
    "expert": 22000.0,
    "specialty": 16000.0,
    "professional": 19000.0,
}

CATEGORY_MULTIPLIERS = {
    "security": 1.25,
    "cybersecurity": 1.25,
    "cloud": 1.15,
    "devops": 1.20,
    "ai/ml": 1.30,
    "data": 1.10,
    "networking": 1.05,
    "software engineering": 1.10,
    "architecture": 1.25,
}

PROVIDER_REPUTATION = {
    "aws": 1.15,
    "microsoft": 1.10,
    "google": 1.12,
    "cisco": 1.10,
    "comptia": 1.00,
    "(isc)²": 1.25,
    "isc2": 1.25,
    "linux foundation": 1.15,
    "hashicorp": 1.12,
    "offensive security": 1.30,
}


@dataclass
class SkillOverlapResult:
    """Quantitative skill and domain overlap between two certifications."""

    cert_a_id: str
    cert_a_title: str
    cert_b_id: str
    cert_b_title: str
    overlap_ratio: float  # 0.0 to 1.0 (Jaccard similarity + semantic boost)
    shared_skills: List[str]
    unique_to_a: List[str]
    unique_to_b: List[str]
    study_hours_saved: int  # Hours saved on Cert B if Cert A is already held
    synergy_discount_pct: float  # 0% to 45% discount on Cert B study duration

    def to_dict(self) -> Dict[str, Any]:
        """Serialize overlap result to dictionary."""
        return {
            "cert_a_id": self.cert_a_id,
            "cert_a_title": self.cert_a_title,
            "cert_b_id": self.cert_b_id,
            "cert_b_title": self.cert_b_title,
            "overlap_ratio": round(self.overlap_ratio, 4),
            "shared_skills": self.shared_skills,
            "unique_to_a": self.unique_to_a,
            "unique_to_b": self.unique_to_b,
            "study_hours_saved": self.study_hours_saved,
            "synergy_discount_pct": round(self.synergy_discount_pct, 1),
        }


@dataclass
class CertROIAnalysis:
    """Financial return on investment analysis for a single certification."""

    cert_id: str
    title: str
    provider: str
    level: str
    exam_cost_usd: float
    estimated_study_hours: int
    annual_salary_premium_usd: float
    payback_period_months: float
    hourly_study_value_usd: float  # Salary premium / study hours
    five_year_net_gain_usd: float  # (5 * annual_premium) - exam_cost
    five_year_roi_pct: float  # (net_gain / exam_cost) * 100
    market_demand_rating: str  # Very High, High, Moderate

    def to_dict(self) -> Dict[str, Any]:
        """Serialize ROI analysis to dictionary."""
        return {
            "cert_id": self.cert_id,
            "title": self.title,
            "provider": self.provider,
            "level": self.level,
            "exam_cost_usd": round(self.exam_cost_usd, 2),
            "estimated_study_hours": self.estimated_study_hours,
            "annual_salary_premium_usd": round(self.annual_salary_premium_usd, 2),
            "payback_period_months": round(self.payback_period_months, 2),
            "hourly_study_value_usd": round(self.hourly_study_value_usd, 2),
            "five_year_net_gain_usd": round(self.five_year_net_gain_usd, 2),
            "five_year_roi_pct": round(self.five_year_roi_pct, 1),
            "market_demand_rating": self.market_demand_rating,
        }


@dataclass
class PortfolioValuation:
    """Aggregate market valuation and diversity metrics for a portfolio of credentials."""

    total_credentials: int
    total_investment_cost_usd: float
    total_study_hours_invested: int
    total_annual_salary_potential_usd: float
    composite_marketability_index: float  # 0 to 100
    vendor_diversification_score: float  # 0 to 100 (low concentration = high score)
    multi_cloud_score: float  # 0 to 100
    security_quotient: float  # 0 to 100
    estimated_salary_range_usd: Tuple[int, int]
    top_synergies: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize portfolio valuation to dictionary."""
        return {
            "total_credentials": self.total_credentials,
            "total_investment_cost_usd": round(self.total_investment_cost_usd, 2),
            "total_study_hours_invested": self.total_study_hours_invested,
            "total_annual_salary_potential_usd": round(self.total_annual_salary_potential_usd, 2),
            "composite_marketability_index": round(self.composite_marketability_index, 1),
            "vendor_diversification_score": round(self.vendor_diversification_score, 1),
            "multi_cloud_score": round(self.multi_cloud_score, 1),
            "security_quotient": round(self.security_quotient, 1),
            "estimated_salary_range_usd": list(self.estimated_salary_range_usd),
            "top_synergies": self.top_synergies,
        }


def _normalize_skill(skill: str) -> str:
    """Normalize skill string for fuzzy matching."""
    s = skill.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return s


def calculate_skill_overlap(cert_a: Certification, cert_b: Certification) -> SkillOverlapResult:
    """Calculate the skill and knowledge overlap between two certifications.
    
    Determines Jaccard similarity between explicit skills plus domain/interest alignment,
    and estimates study hours saved if Cert A is completed before Cert B.
    """
    skills_a_raw = cert_a.skills_gained or []
    skills_b_raw = cert_b.skills_gained or []

    norm_a = {_normalize_skill(s) for s in skills_a_raw if s}
    norm_b = {_normalize_skill(s) for s in skills_b_raw if s}

    # Add interest / domain keywords
    for item in (cert_a.interests or []):
        norm_a.add(_normalize_skill(item))
    for item in (cert_b.interests or []):
        norm_b.add(_normalize_skill(item))

    # Also extract key domain terms from title and category
    norm_a.add(_normalize_skill(cert_a.category))
    norm_b.add(_normalize_skill(cert_b.category))

    intersection = norm_a.intersection(norm_b)
    union = norm_a.union(norm_b)

    # Base Jaccard similarity
    jaccard = len(intersection) / len(union) if union else 0.0

    # Provider and Category boost
    same_provider_boost = 0.15 if cert_a.provider.lower() == cert_b.provider.lower() else 0.0
    same_category_boost = 0.10 if cert_a.category.lower() == cert_b.category.lower() else 0.0

    # Composite overlap ratio capped at 0.85 (some material is always unique)
    overlap_ratio = min(0.85, jaccard + (same_provider_boost * 0.5) + (same_category_boost * 0.5))

    # Shared skills in human-readable form
    shared: List[str] = []
    for sa in skills_a_raw:
        if _normalize_skill(sa) in intersection:
            shared.append(sa)

    # If no explicit shared skills found but overlap exists due to category/provider
    if not shared and (same_provider_boost or same_category_boost):
        shared = [f"Foundational {cert_a.provider} cloud/architecture patterns"]

    unique_a = [s for s in skills_a_raw if s not in shared]
    unique_b = [s for s in skills_b_raw if s not in shared]

    # Synergy discount up to 40% of Cert B study hours
    synergy_discount_pct = min(40.0, overlap_ratio * 50.0)
    hours_saved = int(round((synergy_discount_pct / 100.0) * cert_b.estimated_hours))

    return SkillOverlapResult(
        cert_a_id=cert_a.id,
        cert_a_title=cert_a.title,
        cert_b_id=cert_b.id,
        cert_b_title=cert_b.title,
        overlap_ratio=overlap_ratio,
        shared_skills=shared,
        unique_to_a=unique_a,
        unique_to_b=unique_b,
        study_hours_saved=hours_saved,
        synergy_discount_pct=synergy_discount_pct,
    )


def calculate_cert_roi(cert: Certification) -> CertROIAnalysis:
    """Calculate detailed ROI and salary impact metrics for a certification."""
    level_key = cert.level.lower().strip()
    base_premium = 7000.0
    for k, v in BASE_SALARY_PREMIUM.items():
        if k in level_key:
            base_premium = v
            break

    cat_mult = 1.0
    cat_key = cert.category.lower().strip()
    for k, v in CATEGORY_MULTIPLIERS.items():
        if k in cat_key:
            cat_mult = v
            break

    prov_mult = 1.0
    prov_key = cert.provider.lower().strip()
    for k, v in PROVIDER_REPUTATION.items():
        if k in prov_key:
            prov_mult = v
            break

    salary_premium = base_premium * cat_mult * prov_mult
    cost = max(1.0, cert.cost_usd)  # avoid division by zero
    hours = max(1, cert.estimated_hours)

    payback_months = (cost / salary_premium) * 12.0
    hourly_value = salary_premium / hours
    five_year_net = (salary_premium * 5.0) - cost
    five_year_roi = (five_year_net / cost) * 100.0

    # Market demand rating
    if salary_premium >= 18000.0:
        demand = "Very High"
    elif salary_premium >= 10000.0:
        demand = "High"
    else:
        demand = "Moderate"

    return CertROIAnalysis(
        cert_id=cert.id,
        title=cert.title,
        provider=cert.provider,
        level=cert.level,
        exam_cost_usd=cert.cost_usd,
        estimated_study_hours=cert.estimated_hours,
        annual_salary_premium_usd=salary_premium,
        payback_period_months=payback_months,
        hourly_study_value_usd=hourly_value,
        five_year_net_gain_usd=five_year_net,
        five_year_roi_pct=five_year_roi,
        market_demand_rating=demand,
    )


def evaluate_portfolio(
    cert_ids: Sequence[str],
    catalog: Optional[CertificationCatalog] = None,
) -> PortfolioValuation:
    """Evaluate aggregate compensation potential, marketability, and diversification of a credential set."""
    cat = catalog or CertificationCatalog()
    certs: List[Certification] = []
    for cid in cert_ids:
        c = cat.get(cid)
        if c:
            certs.append(c)

    if not certs:
        return PortfolioValuation(
            total_credentials=0,
            total_investment_cost_usd=0.0,
            total_study_hours_invested=0,
            total_annual_salary_potential_usd=0.0,
            composite_marketability_index=0.0,
            vendor_diversification_score=0.0,
            multi_cloud_score=0.0,
            security_quotient=0.0,
            estimated_salary_range_usd=(65000, 85000),
            top_synergies=[],
        )

    total_cost = sum(c.cost_usd for c in certs)
    total_hours = sum(c.estimated_hours for c in certs)

    # Diminishing returns formula for cumulative salary premium
    # E.g. 1st cert: 100% value, 2nd: 80%, 3rd: 65%, 4th+: 50%
    roi_items = [calculate_cert_roi(c) for c in certs]
    # Sort descending by individual premium
    roi_items.sort(key=lambda x: x.annual_salary_premium_usd, reverse=True)

    cumulative_premium = 0.0
    factors = [1.0, 0.85, 0.70, 0.55, 0.40]
    for idx, item in enumerate(roi_items):
        factor = factors[idx] if idx < len(factors) else 0.30
        cumulative_premium += item.annual_salary_premium_usd * factor

    # Provider diversification (Herfindahl-Hirschman Index inverted)
    provider_counts: Dict[str, int] = {}
    for c in certs:
        p = c.provider.lower().strip()
        provider_counts[p] = provider_counts.get(p, 0) + 1

    total_n = len(certs)
    hhi = sum((count / total_n) ** 2 for count in provider_counts.values())  # 1/N to 1.0
    # Invert HHI: 1.0 (all 1 vendor) -> score 10, 0.2 (balanced) -> score 95
    diversification_score = max(10.0, min(100.0, (1.0 - (hhi - (1.0 / max(1, len(provider_counts))))) * 100.0))

    # Multi-cloud score
    cloud_providers = {"aws", "microsoft", "google", "hashicorp", "linux foundation"}
    present_clouds = {p for p in provider_counts if any(cp in p for cp in cloud_providers)}
    if len(present_clouds) >= 3:
        multi_cloud_score = 95.0
    elif len(present_clouds) == 2:
        multi_cloud_score = 75.0
    elif len(present_clouds) == 1:
        multi_cloud_score = 45.0
    else:
        multi_cloud_score = 15.0

    # Security quotient
    security_certs = [c for c in certs if "security" in c.category.lower() or "security" in c.title.lower()]
    security_quotient = min(100.0, len(security_certs) * 35.0 + (15.0 if security_certs else 0.0))

    # Composite marketability index (weighted 0-100)
    level_weights = {"entry": 10, "associate": 25, "intermediate": 25, "advanced": 40, "expert": 50, "specialty": 40}
    power_points = 0
    for c in certs:
        lvl = c.level.lower().strip()
        pts = 20
        for k, v in level_weights.items():
            if k in lvl:
                pts = v
                break
        power_points += pts

    marketability_index = min(100.0, power_points * 0.75 + (diversification_score * 0.15) + (multi_cloud_score * 0.10))

    # Estimated base salary range
    base_min = 70000 + int(cumulative_premium * 0.8)
    base_max = 95000 + int(cumulative_premium * 1.35)

    # Top synergies within portfolio
    synergies: List[Dict[str, Any]] = []
    if len(certs) >= 2:
        for i in range(len(certs)):
            for j in range(i + 1, len(certs)):
                ov = calculate_skill_overlap(certs[i], certs[j])
                if ov.overlap_ratio >= 0.20:
                    synergies.append({
                        "cert_a": certs[i].title,
                        "cert_b": certs[j].title,
                        "overlap_pct": round(ov.overlap_ratio * 100, 1),
                        "hours_saved": ov.study_hours_saved,
                    })
        synergies.sort(key=lambda x: x["hours_saved"], reverse=True)

    return PortfolioValuation(
        total_credentials=len(certs),
        total_investment_cost_usd=total_cost,
        total_study_hours_invested=total_hours,
        total_annual_salary_potential_usd=cumulative_premium,
        composite_marketability_index=marketability_index,
        vendor_diversification_score=diversification_score,
        multi_cloud_score=multi_cloud_score,
        security_quotient=security_quotient,
        estimated_salary_range_usd=(base_min, base_max),
        top_synergies=synergies[:5],
    )


def format_roi_scorecard(analysis: CertROIAnalysis) -> str:
    """Format single certification ROI scorecard in terminal box."""
    lines = [
        f"╔══════════════════════════════════════════════════════════════════════════╗",
        f"║  ✦ CERTIFICATION ROI & COMPENSATION ANALYSIS                             ║",
        f"╠══════════════════════════════════════════════════════════════════════════╣",
        f"║  Certification:  {analysis.title:<55} ║",
        f"║  Provider/Level: {analysis.provider:<20} | Level: {analysis.level:<24} ║",
        f"╟──────────────────────────────────────────────────────────────────────────╢",
        f"║  • Exam Investment Fee:         ${analysis.exam_cost_usd:<12.2f}                          ║",
        f"║  • Estimated Study Commitment:  {analysis.estimated_study_hours:<4} hours                             ║",
        f"║  • Projected Annual Premium:    ${analysis.annual_salary_premium_usd:<12.2f}/year                      ║",
        f"║  • Investment Payback Horizon:  {analysis.payback_period_months:<4.1f} months                            ║",
        f"║  • Study Hour Return Rate:      ${analysis.hourly_study_value_usd:<6.2f}/hour                           ║",
        f"║  • 5-Year Cumulative Net ROI:   ${analysis.five_year_net_gain_usd:<12.2f} ({analysis.five_year_roi_pct:<5.0f}%)        ║",
        f"║  • Market Demand Index:         {analysis.market_demand_rating:<39} ║",
        f"╚══════════════════════════════════════════════════════════════════════════╝",
    ]
    return "\n".join(lines)


def format_portfolio_scorecard(valuation: PortfolioValuation) -> str:
    """Format portfolio valuation in terminal box."""
    sal_min, sal_max = valuation.estimated_salary_range_usd
    lines = [
        f"╔══════════════════════════════════════════════════════════════════════════╗",
        f"║  ✦ CREDENTIAL PORTFOLIO VALUATION & MARKET POWER                         ║",
        f"╠══════════════════════════════════════════════════════════════════════════╣",
        f"║  Total Credentials Evaluated:   {valuation.total_credentials:<40} ║",
        f"║  Total Direct Exam Investment:  ${valuation.total_investment_cost_usd:<12.2f}                          ║",
        f"║  Total Cumulative Study Hours:  {valuation.total_study_hours_invested:<4} hours                             ║",
        f"║  Projected Added Earning Power: ${valuation.total_annual_salary_potential_usd:<12.2f}/year                      ║",
        f"║  Target Market Salary Range:    ${sal_min:,} - ${sal_max:,}                   ║",
        f"╟──────────────────────────────────────────────────────────────────────────╢",
        f"║  • Marketability Index:         {valuation.composite_marketability_index:>5.1f} / 100                           ║",
        f"║  • Vendor Diversity Score:      {valuation.vendor_diversification_score:>5.1f} / 100                           ║",
        f"║  • Multi-Cloud Readiness:       {valuation.multi_cloud_score:>5.1f} / 100                           ║",
        f"║  • Security Quotient:           {valuation.security_quotient:>5.1f} / 100                           ║",
    ]
    if valuation.top_synergies:
        lines.append(f"╟──────────────────────────────────────────────────────────────────────────╢")
        lines.append(f"║  Top Knowledge Transfer Synergies:                                       ║")
        for syn in valuation.top_synergies:
            syn_str = f"• {syn['cert_a']} -> {syn['cert_b']}: saves ~{syn['hours_saved']}h ({syn['overlap_pct']}%)"
            lines.append(f"║  {syn_str:<72} ║")
    lines.append(f"╚══════════════════════════════════════════════════════════════════════════╝")
    return "\n".join(lines)
