"""Certification lifecycle, validity tracking, and Continuing Professional Education (CPE/CEU) calculation engine.

Models certification validity periods, expiry status, renewal deadlines,
and CPE/CEU credit accumulation across providers (CompTIA, (ISC)², Cisco, AWS, etc.).
100% Python Standard Library. Zero external dependencies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Union


class ExpiryStatus(str, Enum):
    """Lifecycle validity status of a certification."""

    ACTIVE = "active"
    EXPIRING_SOON = "expiring_soon"  # < 90 days
    EXPIRED = "expired"
    LIFETIME = "lifetime"


@dataclass
class CPEActivity:
    """Individual continuing education activity (course, webinar, conference, publication)."""

    activity_id: str
    title: str
    category: str  # Course, Webinar, Conference, Mentoring, Publishing, Volunteer
    cpe_credits: float
    completed_date: str  # ISO YYYY-MM-DD
    provider: Optional[str] = None
    verification_url_or_ref: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CertLifecycleStatus:
    """Detailed validity status and renewal requirements for an earned certification."""

    cert_id: str
    title: str
    provider: str
    earned_date: str  # ISO YYYY-MM-DD
    validity_years: int
    expiry_date: Optional[str]  # None for lifetime
    days_until_expiry: Optional[int]
    status: ExpiryStatus
    required_cpes: int
    earned_cpes: float
    cpe_deficit: float
    annual_maintenance_fee_usd: float

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


# Industry standard validity and CPE renewal requirements by provider
PROVIDER_RENEWAL_SPECS: Dict[str, Dict[str, Any]] = {
    "comptia": {
        "validity_years": 3,
        "cpe_required": 50,  # e.g., Sec+ needs 50 CEUs
        "amf_usd": 50.0,
    },
    "isc2": {
        "validity_years": 3,
        "cpe_required": 120,  # e.g., CISSP needs 120 CPEs (40/year)
        "amf_usd": 135.0,
    },
    "cisco": {
        "validity_years": 3,
        "cpe_required": 80,  # e.g., CCNP needs 80 CE credits or exam
        "amf_usd": 0.0,
    },
    "aws": {
        "validity_years": 3,
        "cpe_required": 0,  # Recertification exam required
        "amf_usd": 0.0,
    },
    "microsoft": {
        "validity_years": 1,  # Annual free online renewal assessment
        "cpe_required": 0,
        "amf_usd": 0.0,
    },
    "google": {
        "validity_years": 2,  # Associate & Professional exams
        "cpe_required": 0,
        "amf_usd": 0.0,
    },
    "offsec": {
        "validity_years": 0,  # Lifetime certifications (OSCP, OSWE, etc.)
        "cpe_required": 0,
        "amf_usd": 0.0,
    },
}


def calculate_lifecycle_status(
    cert_id: str,
    title: str,
    provider: str,
    earned_date_iso: str,
    activities: Sequence[CPEActivity] = (),
    reference_date_iso: Optional[str] = None,
    validity_override_years: Optional[int] = None,
    cpe_override: Optional[int] = None,
) -> CertLifecycleStatus:
    """Calculate the real-time expiry, days remaining, and CPE deficit for a certification.

    Args:
        cert_id: Unique certification ID.
        title: Certification title.
        provider: Issuing organization (e.g. CompTIA, ISC2, AWS, Microsoft).
        earned_date_iso: ISO date string when cert was passed.
        activities: List of CPE activities credited to this certification.
        reference_date_iso: Optional evaluation reference date (defaults to today).
        validity_override_years: Optional override for default validity period.
        cpe_override: Optional override for required CPE credits.

    Returns:
        CertLifecycleStatus: Calculated status report.
    """
    ref_date = date.fromisoformat(reference_date_iso) if reference_date_iso else date.today()
    earned_date = date.fromisoformat(earned_date_iso)

    prov_lower = provider.lower()
    spec: Dict[str, Any] = {"validity_years": 3, "cpe_required": 60, "amf_usd": 0.0}

    for key, s in PROVIDER_RENEWAL_SPECS.items():
        if key in prov_lower:
            spec = s
            break

    validity_years = validity_override_years if validity_override_years is not None else spec["validity_years"]
    cpe_req = cpe_override if cpe_override is not None else spec["cpe_required"]
    amf = spec.get("amf_usd", 0.0)

    # Lifetime certification
    if validity_years <= 0:
        return CertLifecycleStatus(
            cert_id=cert_id,
            title=title,
            provider=provider,
            earned_date=earned_date_iso,
            validity_years=0,
            expiry_date=None,
            days_until_expiry=None,
            status=ExpiryStatus.LIFETIME,
            required_cpes=0,
            earned_cpes=0.0,
            cpe_deficit=0.0,
            annual_maintenance_fee_usd=0.0,
        )

    # Compute expiry date: earned_date + validity_years
    try:
        expiry_date = earned_date.replace(year=earned_date.year + validity_years)
    except ValueError:
        # Leap year fallback (Feb 29 -> Feb 28)
        expiry_date = earned_date + timedelta(days=365 * validity_years)

    days_left = (expiry_date - ref_date).days

    if days_left < 0:
        status = ExpiryStatus.EXPIRED
    elif days_left <= 90:
        status = ExpiryStatus.EXPIRING_SOON
    else:
        status = ExpiryStatus.ACTIVE

    # Sum earned CPE credits
    earned_cpes = sum(act.cpe_credits for act in activities)
    cpe_deficit = max(0.0, float(cpe_req) - earned_cpes)

    return CertLifecycleStatus(
        cert_id=cert_id,
        title=title,
        provider=provider,
        earned_date=earned_date_iso,
        validity_years=validity_years,
        expiry_date=expiry_date.isoformat(),
        days_until_expiry=days_left,
        status=status,
        required_cpes=cpe_req,
        earned_cpes=round(earned_cpes, 1),
        cpe_deficit=round(cpe_deficit, 1),
        annual_maintenance_fee_usd=amf,
    )
