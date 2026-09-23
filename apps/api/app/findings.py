"""Findings: propose-only queue items from checks, scorer, and health alarms."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import DISMISSAL_REASONS, Finding

DAILY_OPEN_CAP = 20
DETECTOR_VERSION = "checks-v1"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def observed_fingerprint(*parts: str) -> str:
    raw = "|".join(parts)
    return sha256(raw.encode()).hexdigest()[:16]


def open_count_today(session: Session, organization_id: UUID) -> int:
    day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        session.scalar(
            select(func.count())
            .select_from(Finding)
            .where(
                Finding.organization_id == organization_id,
                Finding.decision.is_(None),
                Finding.detected_at >= day_start,
            )
        )
        or 0
    )


def create_finding(
    session: Session,
    *,
    organization_id: UUID,
    check_key: str,
    subject_kind: str,
    subject_id: UUID,
    summary_sentence: str,
    observed_value: str | None = None,
    threshold_value: str | None = None,
    evidence: dict | None = None,
    owner_user_id: UUID | None = None,
    fingerprint: str | None = None,
    enforce_daily_cap: bool = True,
) -> Finding | None:
    """Insert a finding unless open-dedupe hits or the daily cap is spent."""
    fp = fingerprint or observed_fingerprint(observed_value or "", summary_sentence)
    dedupe_key = f"{check_key}:{subject_id}:{fp}"
    existing = session.scalar(select(Finding).where(Finding.dedupe_key == dedupe_key))
    if existing is not None and existing.decision is None:
        return existing
    if enforce_daily_cap and open_count_today(session, organization_id) >= DAILY_OPEN_CAP:
        return None
    finding = Finding(
        organization_id=organization_id,
        owner_user_id=owner_user_id,
        check_key=check_key,
        subject_kind=subject_kind,
        subject_id=subject_id,
        observed_value=observed_value,
        threshold_value=threshold_value,
        summary_sentence=summary_sentence,
        evidence=evidence or {},
        detected_at=utcnow(),
        detector_version=DETECTOR_VERSION,
        # A prior *dismissed* finding may hold this key; mint a fresh one so it re-raises.
        dedupe_key=dedupe_key if existing is None else f"{dedupe_key}:{int(utcnow().timestamp())}",
    )
    try:
        with session.begin_nested():
            session.add(finding)
            session.flush()
    except IntegrityError:
        return session.scalar(select(Finding).where(Finding.dedupe_key == finding.dedupe_key))
    return finding


def dismiss_finding(
    session: Session,
    finding: Finding,
    *,
    user_id: UUID,
    reason: str,
) -> Finding:
    if reason not in DISMISSAL_REASONS:
        raise ValueError(f"invalid_dismissal_reason:{reason}")
    finding.decision = "dismissed"
    finding.dismissal_reason = reason
    finding.decided_by_user_id = user_id
    finding.decided_at = utcnow()
    session.flush()
    return finding
