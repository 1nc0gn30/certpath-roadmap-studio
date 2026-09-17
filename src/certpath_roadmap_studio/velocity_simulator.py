"""Learning Velocity Simulator & Monte Carlo Timeline Optimization Engine.

Provides stochastic completion timeline projections, cognitive fatigue / burnout analysis,
exam retake risk modeling, and multi-scenario study pacing optimizations for
certification roadmaps.

Zero third-party runtime dependencies (100% Python Standard Library).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
import math
import random
from typing import Any, Dict, List, Optional, Sequence, Union

from .catalog import Certification
from .roadmap_planner import RoadmapPlan


class ExperienceLevel(str, Enum):
    """User baseline experience tier adjusting learning speed and first-try pass probability."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"

    @property
    def speed_multiplier(self) -> float:
        """Study hours scaling factor (higher means faster learning, fewer hours needed)."""
        mapping = {
            ExperienceLevel.BEGINNER: 0.80,       # 25% more hours
            ExperienceLevel.INTERMEDIATE: 1.00,   # Baseline standard hours
            ExperienceLevel.ADVANCED: 1.25,       # 20% fewer hours
            ExperienceLevel.EXPERT: 1.50,         # 33% fewer hours
        }
        return mapping[self]

    @property
    def base_pass_rate(self) -> float:
        """Baseline probability of clearing an intermediate examination on the first attempt."""
        mapping = {
            ExperienceLevel.BEGINNER: 0.70,
            ExperienceLevel.INTERMEDIATE: 0.82,
            ExperienceLevel.ADVANCED: 0.92,
            ExperienceLevel.EXPERT: 0.97,
        }
        return mapping[self]


@dataclass
class FatigueWarning:
    """Fatigue or cognitive overload indicator on a specific milestone."""

    cert_id: str
    title: str
    burnout_score: float  # 0.0 to 1.0
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    consecutive_hard_exams: int
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert warning to dictionary."""
        return {
            "cert_id": self.cert_id,
            "title": self.title,
            "burnout_score": round(self.burnout_score, 2),
            "risk_level": self.risk_level,
            "consecutive_hard_exams": self.consecutive_hard_exams,
            "recommendation": self.recommendation,
        }


@dataclass
class MilestoneTimelineItem:
    """Projected milestone schedule date and risk telemetry."""

    index: int
    cert_id: str
    title: str
    provider: str
    level: str
    nominal_hours: int
    adjusted_hours: float
    estimated_weeks: float
    start_date_iso: str
    completion_date_iso: str
    pass_probability: float
    expected_cost: float
    burnout_score: float
    decompression_days: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert milestone item to dictionary."""
        return {
            "index": self.index,
            "cert_id": self.cert_id,
            "title": self.title,
            "provider": self.provider,
            "level": self.level,
            "nominal_hours": self.nominal_hours,
            "adjusted_hours": round(self.adjusted_hours, 1),
            "estimated_weeks": round(self.estimated_weeks, 1),
            "start_date_iso": self.start_date_iso,
            "completion_date_iso": self.completion_date_iso,
            "pass_probability": round(self.pass_probability, 3),
            "expected_cost": round(self.expected_cost, 2),
            "burnout_score": round(self.burnout_score, 2),
            "decompression_days": self.decompression_days,
        }


@dataclass
class MonteCarloSummary:
    """Aggregated statistics across stochastic Monte Carlo simulation runs."""

    trials_count: int
    weeks_p50: float
    weeks_p80: float
    weeks_p95: float
    cost_p50: float
    cost_p80: float
    cost_p95: float
    completion_date_p50: str
    completion_date_p80: str
    completion_date_p95: str
    retakes_p50: float
    retakes_p95: float
    top_bottlenecks: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert Monte Carlo summary to dictionary."""
        return {
            "trials_count": self.trials_count,
            "weeks_p50": round(self.weeks_p50, 1),
            "weeks_p80": round(self.weeks_p80, 1),
            "weeks_p95": round(self.weeks_p95, 1),
            "cost_p50": round(self.cost_p50, 2),
            "cost_p80": round(self.cost_p80, 2),
            "cost_p95": round(self.cost_p95, 2),
            "completion_date_p50": self.completion_date_p50,
            "completion_date_p80": self.completion_date_p80,
            "completion_date_p95": self.completion_date_p95,
            "retakes_p50": round(self.retakes_p50, 1),
            "retakes_p95": round(self.retakes_p95, 1),
            "top_bottlenecks": self.top_bottlenecks,
        }


@dataclass
class VelocitySimulationReport:
    """Comprehensive output of learning velocity modeling and Monte Carlo simulations."""

    target_name: str
    experience_level: str
    weekly_hours: float
    learning_speed_multiplier: float
    total_nominal_hours: int
    total_adjusted_hours: float
    fatigue_index: float  # 0 to 100
    fatigue_warnings: List[FatigueWarning]
    milestones: List[MilestoneTimelineItem]
    monte_carlo: MonteCarloSummary
    pacing_recommendation: str
    ascii_burndown_chart: str
    sensitivity_matrix: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize complete report to nested dictionary."""
        return {
            "target_name": self.target_name,
            "experience_level": self.experience_level,
            "weekly_hours": self.weekly_hours,
            "learning_speed_multiplier": round(self.learning_speed_multiplier, 2),
            "total_nominal_hours": self.total_nominal_hours,
            "total_adjusted_hours": round(self.total_adjusted_hours, 1),
            "fatigue_index": round(self.fatigue_index, 1),
            "fatigue_warnings": [w.to_dict() for w in self.fatigue_warnings],
            "milestones": [m.to_dict() for m in self.milestones],
            "monte_carlo": self.monte_carlo.to_dict(),
            "pacing_recommendation": self.pacing_recommendation,
            "ascii_burndown_chart": self.ascii_burndown_chart,
            "sensitivity_matrix": self.sensitivity_matrix,
        }


def _extract_cert_list(plan_or_certs: Union[RoadmapPlan, Sequence[Certification]]) -> Tuple[str, List[Certification], int, float]:
    """Extract list of certifications, target title, weekly hours, and cost."""
    if isinstance(plan_or_certs, RoadmapPlan):
        title = plan_or_certs.target_name
        certs = list(plan_or_certs.all_certifications)
        weekly_hours = plan_or_certs.weekly_hours or 10
        total_cost = plan_or_certs.total_cost_usd
    else:
        certs = list(plan_or_certs)
        title = certs[-1].title if certs else "Custom Certification Path"
        weekly_hours = 10
        total_cost = sum(c.cost_usd for c in certs)

    return title, certs, weekly_hours, total_cost


def _calculate_cert_pass_prob(cert: Certification, exp: ExperienceLevel) -> float:
    """Calculate realistic first-attempt pass probability given difficulty and experience."""
    base_p = exp.base_pass_rate
    lvl = cert.level.lower()
    if "entry" in lvl or "foundational" in lvl:
        diff_penalty = 0.05
    elif "advanced" in lvl or "expert" in lvl or "specialty" in lvl or "professional" in lvl:
        diff_penalty = 0.22
    else:
        diff_penalty = 0.12

    # Higher estimated hours indicate broader/heavier syllabi
    hours_penalty = min(0.12, max(0.0, (cert.estimated_hours - 60) * 0.001))
    prob = max(0.35, min(0.99, base_p - diff_penalty - hours_penalty))
    return prob


def generate_ascii_burndown(
    total_hours: float,
    weekly_hours: float,
    total_weeks: float,
    width: int = 40,
) -> str:
    """Generate clean ASCII burndown chart visualization of study trajectory."""
    if total_hours <= 0 or weekly_hours <= 0:
        return "No study hours to plot."

    steps = 10
    interval = total_weeks / steps if steps > 0 else 1.0
    lines = [
        "✦ Target Roadmap Study Burndown Trajectory ✦",
        f"  Total Effort: {total_hours:.0f}h  |  Pacing: {weekly_hours:.0f}h/week  |  Estimated: {total_weeks:.1f} weeks",
        "",
        "  Week    Hours Rem.  Progress",
    ]

    for step in range(steps + 1):
        w = step * interval
        hours_done = min(total_hours, w * weekly_hours)
        hours_rem = max(0.0, total_hours - hours_done)
        pct = (hours_done / total_hours) if total_hours > 0 else 1.0

        bar_len = int(pct * width)
        bar = "█" * bar_len + "░" * (width - bar_len)
        lines.append(f"  W{w:04.1f}   {hours_rem:6.0f}h   [{bar}] {pct * 100:5.1f}%")

    return "\n".join(lines)


def calculate_pacing_sensitivity(
    plan_or_certs: Union[RoadmapPlan, Sequence[Certification]],
    experience_level: Union[ExperienceLevel, str] = ExperienceLevel.INTERMEDIATE,
    hours_options: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """Compute sensitivity comparison matrix across varying weekly study commitments."""
    if isinstance(experience_level, str):
        try:
            exp = ExperienceLevel(experience_level.lower())
        except ValueError:
            exp = ExperienceLevel.INTERMEDIATE
    else:
        exp = experience_level

    _, certs, _, _ = _extract_cert_list(plan_or_certs)
    nom_hours = sum(c.estimated_hours for c in certs)
    adj_hours = nom_hours / exp.speed_multiplier

    if not hours_options:
        hours_options = [5, 10, 15, 20, 25]

    matrix = []
    for h in hours_options:
        if h <= 0:
            continue
        weeks = adj_hours / h
        months = weeks / 4.33
        intensity = "Casual" if h <= 7 else ("Steady" if h <= 15 else ("Intensive" if h <= 24 else "Bootcamp"))
        matrix.append({
            "weekly_hours": h,
            "intensity_tier": intensity,
            "estimated_weeks": round(weeks, 1),
            "estimated_months": round(months, 1),
            "hours_required": round(adj_hours, 1),
        })

    return matrix


def simulate_velocity(
    plan_or_certs: Union[RoadmapPlan, Sequence[Certification]],
    weekly_hours: Optional[float] = None,
    experience_level: Union[ExperienceLevel, str] = ExperienceLevel.INTERMEDIATE,
    start_date: Optional[datetime.date] = None,
    simulation_trials: int = 500,
    random_seed: Optional[int] = 42,
) -> VelocitySimulationReport:
    """Run full velocity simulation with cognitive fatigue analysis and Monte Carlo trials."""
    if isinstance(experience_level, str):
        try:
            exp = ExperienceLevel(experience_level.lower())
        except ValueError:
            exp = ExperienceLevel.INTERMEDIATE
    else:
        exp = experience_level

    title, certs, def_weekly, _ = _extract_cert_list(plan_or_certs)
    pace_hours = float(weekly_hours if weekly_hours is not None and weekly_hours > 0 else def_weekly)
    if pace_hours <= 0:
        pace_hours = 10.0

    current_date = start_date or datetime.date.today()

    nom_total = sum(c.estimated_hours for c in certs)
    adj_total = nom_total / exp.speed_multiplier

    # 1. Milestone Timeline & Fatigue Modeling
    milestones: List[MilestoneTimelineItem] = []
    warnings: List[FatigueWarning] = []

    consecutive_hard = 0
    cumulative_fatigue = 0.0

    cal_date = current_date

    for idx, cert in enumerate(certs, start=1):
        c_adj_hours = cert.estimated_hours / exp.speed_multiplier
        c_weeks = c_adj_hours / pace_hours
        study_days = int(math.ceil(c_weeks * 7.0))

        # Pass probability
        p_pass = _calculate_cert_pass_prob(cert, exp)

        # Expected cost with retake factor
        expected_retakes = (1.0 - p_pass)
        expected_cost = cert.cost_usd + (expected_retakes * cert.cost_usd)

        # Fatigue & cognitive load calculation
        lvl = cert.level.lower()
        is_hard = "advanced" in lvl or "expert" in lvl or cert.estimated_hours >= 100

        if is_hard:
            consecutive_hard += 1
            fatigue_increment = 0.28 + (0.12 * consecutive_hard)
        else:
            consecutive_hard = max(0, consecutive_hard - 1)
            fatigue_increment = 0.08

        # Burnout score (0.0 to 1.0)
        burnout = min(1.0, 0.15 + (fatigue_increment * 1.5) + (0.10 * consecutive_hard))
        cumulative_fatigue += burnout

        # Decompression period
        decompression_days = 0
        if consecutive_hard >= 2:
            decompression_days = 7 * consecutive_hard
            risk = "HIGH" if consecutive_hard == 2 else "CRITICAL"
            warnings.append(
                FatigueWarning(
                    cert_id=cert.id,
                    title=cert.title,
                    burnout_score=burnout,
                    risk_level=risk,
                    consecutive_hard_exams=consecutive_hard,
                    recommendation=(
                        f"Consecutive high-difficulty exams detected ({consecutive_hard} in a row). "
                        f"Schedule a {decompression_days}-day decompression buffer before or after '{cert.title}', "
                        "or intersperse a lighter foundational certification."
                    ),
                )
            )
        elif burnout > 0.65:
            decompression_days = 4
            warnings.append(
                FatigueWarning(
                    cert_id=cert.id,
                    title=cert.title,
                    burnout_score=burnout,
                    risk_level="MEDIUM",
                    consecutive_hard_exams=consecutive_hard,
                    recommendation=(
                        f"Heavy cognitive load expected for '{cert.title}'. "
                        "Recommend spacing study blocks and taking 4 days rest prior to examination."
                    ),
                )
            )

        start_iso = cal_date.isoformat()
        comp_date = cal_date + datetime.timedelta(days=study_days)
        comp_iso = comp_date.isoformat()

        # Advance calendar including decompression buffer
        cal_date = comp_date + datetime.timedelta(days=decompression_days)

        milestones.append(
            MilestoneTimelineItem(
                index=idx,
                cert_id=cert.id,
                title=cert.title,
                provider=cert.provider,
                level=cert.level,
                nominal_hours=cert.estimated_hours,
                adjusted_hours=c_adj_hours,
                estimated_weeks=c_weeks,
                start_date_iso=start_iso,
                completion_date_iso=comp_iso,
                pass_probability=p_pass,
                expected_cost=expected_cost,
                burnout_score=burnout,
                decompression_days=decompression_days,
            )
        )

    # Normalized overall fatigue index (0 to 100)
    avg_fatigue = (cumulative_fatigue / len(certs)) if certs else 0.0
    overall_fatigue_index = min(100.0, avg_fatigue * 100.0)

    # 2. Monte Carlo Simulation Engine
    rng = random.Random(random_seed) if random_seed is not None else random.Random()
    trials_count = max(50, min(10000, simulation_trials))

    trial_weeks: List[float] = []
    trial_costs: List[float] = []
    trial_retakes: List[int] = []
    bottleneck_counts: Dict[str, int] = {c.id: 0 for c in certs}

    for _ in range(trials_count):
        total_trial_hours = 0.0
        total_trial_cost = 0.0
        total_trial_retakes = 0
        trial_max_delay = -1.0
        trial_bottleneck = certs[0].id if certs else ""

        for cert in certs:
            p_pass = _calculate_cert_pass_prob(cert, exp)

            # Log-normal or gaussian speed fluctuation (mean 1.0, std dev 0.15)
            fluctuation = max(0.65, min(1.50, rng.gauss(1.0, 0.15)))
            cert_study_hours = (cert.estimated_hours / exp.speed_multiplier) * fluctuation
            total_trial_hours += cert_study_hours
            total_trial_cost += cert.cost_usd

            # Exam pass/fail attempts
            attempts = 1
            while attempts <= 4:
                if rng.random() <= p_pass:
                    break
                # Failed attempt: add retake study cool-off and exam fee
                attempts += 1
                total_trial_retakes += 1
                retake_study_hours = max(15.0, cert_study_hours * 0.35)
                total_trial_hours += retake_study_hours
                total_trial_cost += cert.cost_usd

                delay_hours = retake_study_hours
                if delay_hours > trial_max_delay:
                    trial_max_delay = delay_hours
                    trial_bottleneck = cert.id

        t_weeks = total_trial_hours / pace_hours
        trial_weeks.append(t_weeks)
        trial_costs.append(total_trial_cost)
        trial_retakes.append(total_trial_retakes)
        if trial_bottleneck:
            bottleneck_counts[trial_bottleneck] += 1

    # Sort distributions for percentiles
    trial_weeks.sort()
    trial_costs.sort()
    trial_retakes.sort()

    def _get_percentile(data: List[float], p: float) -> float:
        if not data:
            return 0.0
        idx = int(math.ceil(p * len(data))) - 1
        idx = max(0, min(len(data) - 1, idx))
        return data[idx]

    w_p50 = _get_percentile(trial_weeks, 0.50)
    w_p80 = _get_percentile(trial_weeks, 0.80)
    w_p95 = _get_percentile(trial_weeks, 0.95)

    c_p50 = _get_percentile(trial_costs, 0.50)
    c_p80 = _get_percentile(trial_costs, 0.80)
    c_p95 = _get_percentile(trial_costs, 0.95)

    r_p50 = float(_get_percentile([float(x) for x in trial_retakes], 0.50))
    r_p95 = float(_get_percentile([float(x) for x in trial_retakes], 0.95))

    comp_p50 = (current_date + datetime.timedelta(days=int(w_p50 * 7))).isoformat()
    comp_p80 = (current_date + datetime.timedelta(days=int(w_p80 * 7))).isoformat()
    comp_p95 = (current_date + datetime.timedelta(days=int(w_p95 * 7))).isoformat()

    # Top bottlenecks
    sorted_bottlenecks = sorted(bottleneck_counts.items(), key=lambda x: x[1], reverse=True)
    top_bottlenecks = [
        {"cert_id": cid, "delay_frequency_pct": round((cnt / trials_count) * 100, 1)}
        for cid, cnt in sorted_bottlenecks[:3]
        if cnt > 0
    ]

    mc_summary = MonteCarloSummary(
        trials_count=trials_count,
        weeks_p50=w_p50,
        weeks_p80=w_p80,
        weeks_p95=w_p95,
        cost_p50=c_p50,
        cost_p80=c_p80,
        cost_p95=c_p95,
        completion_date_p50=comp_p50,
        completion_date_p80=comp_p80,
        completion_date_p95=comp_p95,
        retakes_p50=r_p50,
        retakes_p95=r_p95,
        top_bottlenecks=top_bottlenecks,
    )

    # 3. Pacing Recommendations
    if overall_fatigue_index >= 70:
        pacing_rec = (
            f"High Burnout Risk ({overall_fatigue_index:.0f}/100). Consider capping study time to "
            f"{max(6.0, pace_hours * 0.75):.0f}h/week or introducing 1-2 week scheduled recovery blocks."
        )
    elif overall_fatigue_index >= 45:
        pacing_rec = (
            f"Moderate Cognitive Load ({overall_fatigue_index:.0f}/100). Recommended steady pacing "
            f"at {pace_hours:.0f}h/week with weekends preserved for practice labs."
        )
    else:
        pacing_rec = (
            f"Healthy Sustainable Pacing ({overall_fatigue_index:.0f}/100). Pace of {pace_hours:.0f}h/week "
            "is well-balanced for long-term retention."
        )

    # 4. ASCII Burndown & Sensitivity Matrix
    ascii_chart = generate_ascii_burndown(
        total_hours=adj_total,
        weekly_hours=pace_hours,
        total_weeks=w_p50,
        width=36,
    )

    sensitivity_matrix = calculate_pacing_sensitivity(
        plan_or_certs=certs,
        experience_level=exp,
    )

    return VelocitySimulationReport(
        target_name=title,
        experience_level=exp.value,
        weekly_hours=pace_hours,
        learning_speed_multiplier=exp.speed_multiplier,
        total_nominal_hours=nom_total,
        total_adjusted_hours=adj_total,
        fatigue_index=overall_fatigue_index,
        fatigue_warnings=warnings,
        milestones=milestones,
        monte_carlo=mc_summary,
        pacing_recommendation=pacing_rec,
        ascii_burndown_chart=ascii_chart,
        sensitivity_matrix=sensitivity_matrix,
    )
