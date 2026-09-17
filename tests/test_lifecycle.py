"""Unit tests for certification lifecycle, expiration tracking, and CPE calculation engine."""

import pytest
from certpath_roadmap_studio import (
    CPEActivity,
    CertLifecycleStatus,
    ExpiryStatus,
    calculate_lifecycle_status,
)


def test_active_certification_status():
    status = calculate_lifecycle_status(
        cert_id="comptia-sec-plus",
        title="CompTIA Security+",
        provider="CompTIA",
        earned_date_iso="2025-01-01",
        reference_date_iso="2025-06-01",
    )
    assert status.status == ExpiryStatus.ACTIVE
    assert status.validity_years == 3
    assert status.days_until_expiry is not None and status.days_until_expiry > 90
    assert status.required_cpes == 50
    assert status.earned_cpes == 0.0
    assert status.cpe_deficit == 50.0


def test_expiring_soon_status_with_cpes():
    activities = [
        CPEActivity(
            activity_id="act-1",
            title="Cloud Security Summit Webinar",
            category="Webinar",
            cpe_credits=15.0,
            completed_date="2027-10-01",
        ),
        CPEActivity(
            activity_id="act-2",
            title="Penetration Testing Course",
            category="Course",
            cpe_credits=30.0,
            completed_date="2027-11-01",
        ),
    ]

    status = calculate_lifecycle_status(
        cert_id="comptia-sec-plus",
        title="CompTIA Security+",
        provider="CompTIA",
        earned_date_iso="2025-01-01",
        activities=activities,
        reference_date_iso="2027-11-15",  # ~47 days before 2028-01-01 expiry
    )
    assert status.status == ExpiryStatus.EXPIRING_SOON
    assert status.days_until_expiry is not None and 0 < status.days_until_expiry <= 90
    assert status.earned_cpes == 45.0
    assert status.cpe_deficit == 5.0  # 50 - 45


def test_expired_certification_status():
    status = calculate_lifecycle_status(
        cert_id="aws-saa",
        title="AWS Solutions Architect Associate",
        provider="AWS",
        earned_date_iso="2020-01-01",
        reference_date_iso="2025-01-01",
    )
    assert status.status == ExpiryStatus.EXPIRED
    assert status.days_until_expiry is not None and status.days_until_expiry < 0


def test_lifetime_certification_status():
    status = calculate_lifecycle_status(
        cert_id="offsec-oscp",
        title="OffSec Certified Professional",
        provider="OffSec",
        earned_date_iso="2022-05-15",
    )
    assert status.status == ExpiryStatus.LIFETIME
    assert status.expiry_date is None
    assert status.days_until_expiry is None
    assert status.required_cpes == 0
    assert status.cpe_deficit == 0.0
