"""Health (#21), findings queue (#15), job observability (#31) and nightly test runs (#19).

#102 extends this with per-template ladder metrics and a golden panel — additive
only; existing alarms / windows / jobs shape is preserved.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import get_current_user
from .database import get_session
from .findings import create_finding, dismiss_finding
from .golden import acceptance_for_template, fixture_golden_metrics, golden_panel
from .models import (
    DISMISSAL_REASONS,
    STACK_TYPES,
    ConfirmEvent,
    Finding,
    KnowledgeJob,
    Organization,
    Spend,
    Substack,
    SubstackContent,
    TestRun,
    User,
)
from .spend import tokens_used_today

router = APIRouter(tags=["health"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def per_template_metrics(
    session: Session,
    organization_id: UUID,
    since: datetime,
    golden_metrics: dict,
) -> list[dict]:
    """Review rate, edit count and acceptance per stack/template key (7d window).

    Counts only — no PO content, file names, product names or prices.
    ``review_rate`` = person confirms / all confirms for that template.
    ``edit_count`` = sum of (revision - 1) on contents confirmed in the window
    (extra revisions stand in for edits until dedicated edit telemetry lands).
    ``acceptance`` comes from the golden panel (fixture until #106 live cut).
    """
    confirm_rows = session.execute(
        select(Substack.stack_type, ConfirmEvent.kind, func.count())
        .join(Substack, Substack.id == ConfirmEvent.substack_id)
        .where(
            ConfirmEvent.organization_id == organization_id,
            ConfirmEvent.at >= since,
        )
        .group_by(Substack.stack_type, ConfirmEvent.kind)
    ).all()
    by_key: dict[str, dict[str, int]] = {}
    for stack_type, kind, count in confirm_rows:
        bucket = by_key.setdefault(stack_type, {"person": 0, "bulk": 0, "auto": 0})
        if kind in bucket:
            bucket[kind] = count

    edit_rows = session.execute(
        select(
            Substack.stack_type,
            func.coalesce(func.sum(SubstackContent.revision - 1), 0),
        )
        .join(Substack, Substack.id == SubstackContent.substack_id)
        .where(
            Substack.organization_id == organization_id,
            SubstackContent.confirmed_at.is_not(None),
            SubstackContent.confirmed_at >= since,
            SubstackContent.revision > 1,
        )
        .group_by(Substack.stack_type)
    ).all()
    edits = {stack_type: int(total) for stack_type, total in edit_rows}

    # Include every known stack type plus any orphan keys seen in confirms.
    keys = list(STACK_TYPES) + [key for key in by_key if key not in STACK_TYPES]
    result: list[dict] = []
    for key in keys:
        kinds = by_key.get(key, {"person": 0, "bulk": 0, "auto": 0})
        total = kinds["person"] + kinds["bulk"] + kinds["auto"]
        review_rate = (kinds["person"] / total) if total else 0.0
        result.append(
            {
                "template_or_stack_key": key,
                "review_rate": review_rate,
                "edit_count": edits.get(key, 0),
                "acceptance": acceptance_for_template(golden_metrics, key),
            }
        )
    return result


class DismissBody(BaseModel):
    reason: str


@router.get("/accounts/{organization_id}/health")
def get_health(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    now = utcnow()
    windows = {"7d": now - timedelta(days=7), "28d": now - timedelta(days=28)}

    def confirm_counts(since: datetime) -> dict:
        rows = session.execute(
            select(ConfirmEvent.kind, func.count())
            .where(
                ConfirmEvent.organization_id == organization_id,
                ConfirmEvent.at >= since,
            )
            .group_by(ConfirmEvent.kind)
        ).all()
        base = {"person": 0, "bulk": 0, "auto": 0}
        for kind, count in rows:
            base[kind] = count
        return base

    def finding_stats(since: datetime) -> dict:
        raised = session.scalar(
            select(func.count()).select_from(Finding).where(
                Finding.organization_id == organization_id,
                Finding.detected_at >= since,
            )
        ) or 0
        dismissed = session.scalar(
            select(func.count()).select_from(Finding).where(
                Finding.organization_id == organization_id,
                Finding.detected_at >= since,
                Finding.decision == "dismissed",
            )
        ) or 0
        open_count = session.scalar(
            select(func.count()).select_from(Finding).where(
                Finding.organization_id == organization_id,
                Finding.decision.is_(None),
            )
        ) or 0
        per_check = session.execute(
            select(Finding.check_key, func.count())
            .where(
                Finding.organization_id == organization_id,
                Finding.detected_at >= since,
            )
            .group_by(Finding.check_key)
        ).all()
        return {
            "raised": raised,
            "dismissed": dismissed,
            "open": open_count,
            "dismiss_rate": (dismissed / raised) if raised else 0.0,
            "per_check": {key: count for key, count in per_check},
        }

    alarms: list[dict] = []
    findings_7 = finding_stats(windows["7d"])
    if findings_7["dismiss_rate"] > 0.20 and findings_7["raised"] >= 5:
        alarms.append({"key": "dismiss_rate", "message": "Dismiss rate over 20% this week."})

    oldest_open = session.scalar(
        select(func.min(Finding.detected_at)).where(
            Finding.organization_id == organization_id,
            Finding.decision.is_(None),
        )
    )
    if oldest_open is not None and oldest_open < now - timedelta(days=3):
        alarms.append({"key": "queue_age", "message": "Queue items older than 3 days."})

    last_test = session.scalar(
        select(TestRun)
        .where(
            TestRun.organization_id == organization_id,
            TestRun.kind == "retrieval",
        )
        .order_by(TestRun.started_at.desc())
        .limit(1)
    )
    test_summary = None
    if last_test is not None:
        recall = (last_test.metrics or {}).get("recall_at_5_mean")
        test_summary = {
            "status": last_test.status,
            "started_at": last_test.started_at.isoformat(),
            "recall_at_5_mean": recall,
        }
        if last_test.status == "failed" or (
            last_test.status == "passed"
            and isinstance(recall, (int, float))
            and recall < 0.8
        ):
            alarms.append({"key": "nightly_recall", "message": "Nightly retrieval test needs attention."})

    confirms_7 = confirm_counts(windows["7d"])
    bulk_share = 0.0
    total_confirms = sum(confirms_7.values())
    if total_confirms:
        bulk_share = confirms_7["bulk"] / total_confirms
        if bulk_share > 0.5 and total_confirms >= 10:
            alarms.append({"key": "bulk_confirm_share", "message": "Bulk confirms dominate this week."})

    spend_today = tokens_used_today(session, organization_id)
    org = session.get(Organization, organization_id)
    budget = org.daily_token_budget if org is not None else 500_000
    if spend_today >= budget:
        alarms.append({"key": "model_spend", "message": "Model spend is over the daily cap."})

    spend_7 = session.scalar(
        select(func.coalesce(func.sum(Spend.input_tokens + Spend.output_tokens), 0)).where(
            Spend.organization_id == organization_id,
            Spend.day >= (now - timedelta(days=7)).date(),
        )
    ) or 0
    spend_28 = session.scalar(
        select(func.coalesce(func.sum(Spend.input_tokens + Spend.output_tokens), 0)).where(
            Spend.organization_id == organization_id,
            Spend.day >= (now - timedelta(days=28)).date(),
        )
    ) or 0

    queue_depth = session.scalar(
        select(func.count()).select_from(KnowledgeJob).where(
            KnowledgeJob.organization_id == organization_id,
            KnowledgeJob.status.in_(("queued", "running", "budget_exhausted")),
        )
    ) or 0
    failures_24h = session.scalar(
        select(func.count()).select_from(KnowledgeJob).where(
            KnowledgeJob.organization_id == organization_id,
            KnowledgeJob.status == "failed",
            KnowledgeJob.updated_at >= now - timedelta(hours=24),
        )
    ) or 0
    jobs = {
        "queue_depth": queue_depth,
        "failures_last_24h": failures_24h,
    }

    # Persist alarms as findings so they land in To check.
    for alarm in alarms:
        create_finding(
            session,
            organization_id=organization_id,
            check_key=f"health_{alarm['key']}",
            subject_kind="organization",
            subject_id=organization_id,
            summary_sentence=alarm["message"],
            observed_value=alarm["key"],
            fingerprint=f"{alarm['key']}:{now.date().isoformat()}",
        )
    session.commit()

    test_ok = last_test is not None and last_test.status == "passed"
    test_pending = last_test is None or last_test.status == "skipped"
    if not alarms and test_ok:
        rest_line = "Nothing to act on. Last night's test passed."
    elif not alarms and test_pending:
        rest_line = "Nothing to act on. Nightly test has not run with labels yet."
    elif alarms:
        rest_line = alarms[0]["message"]
    else:
        rest_line = "Review open findings."

    golden = golden_panel(session, organization_id)
    per_template = per_template_metrics(
        session,
        organization_id,
        windows["7d"],
        golden.get("metrics") or {},
    )

    return {
        "at_rest": rest_line,
        "alarms": alarms,
        "windows": {
            "7d": {
                "confirms": confirm_counts(windows["7d"]),
                "findings": findings_7,
                "model_spend_tokens": int(spend_7),
            },
            "28d": {
                "confirms": confirm_counts(windows["28d"]),
                "findings": finding_stats(windows["28d"]),
                "model_spend_tokens": int(spend_28),
            },
        },
        "nightly_test": test_summary,
        # Harness/fixture metrics only until live golden cut (#106).
        "golden": fixture_golden_metrics(),
        "queue_depth": queue_depth,
        "jobs": jobs,
        "model_spend_tokens_today": spend_today,
        "daily_token_budget": budget,
        # #102 — ladder metrics + golden panel (extend, do not replace above).
        "per_template": per_template,
        "golden": golden,
    }


@router.get("/accounts/{organization_id}/findings")
def list_findings(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Open findings the caller may see: org-wide ones plus their own owner-only ones."""
    membership_for(organization_id, user, session)
    rows = session.scalars(
        select(Finding)
        .where(
            Finding.organization_id == organization_id,
            Finding.decision.is_(None),
            or_(Finding.owner_user_id.is_(None), Finding.owner_user_id == user.id),
        )
        .order_by(Finding.detected_at.desc())
        .limit(100)
    ).all()
    return {
        "findings": [
            {
                "id": str(f.id),
                "check_key": f.check_key,
                "summary_sentence": f.summary_sentence,
                "detected_at": f.detected_at.isoformat(),
                "subject_kind": f.subject_kind,
                "subject_id": str(f.subject_id),
            }
            for f in rows
        ],
        "dismissal_reasons": list(DISMISSAL_REASONS),
    }


@router.post("/accounts/{organization_id}/findings/{finding_id}/dismiss")
def dismiss(
    organization_id: UUID,
    finding_id: UUID,
    body: DismissBody,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    finding = session.get(Finding, finding_id)
    if finding is None or finding.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="finding_not_found")
    try:
        dismiss_finding(session, finding, user_id=user.id, reason=body.reason)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    session.commit()
    return {"id": str(finding.id), "decision": finding.decision, "dismissal_reason": finding.dismissal_reason}


@router.get("/accounts/{organization_id}/jobs")
def get_jobs(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Queue depth, oldest queued age, failures in the last 24h, counts per kind and status."""
    membership_for(organization_id, user, session)
    now = utcnow()
    queued = session.scalars(
        select(KnowledgeJob).where(
            KnowledgeJob.organization_id == organization_id,
            KnowledgeJob.status == "queued",
        )
    ).all()
    oldest_age = None
    if queued:
        oldest = min(job.created_at for job in queued)
        oldest_age = int((now - oldest).total_seconds())
    failures = session.scalar(
        select(func.count()).select_from(KnowledgeJob).where(
            KnowledgeJob.organization_id == organization_id,
            KnowledgeJob.status == "failed",
            KnowledgeJob.updated_at >= now - timedelta(hours=24),
        )
    ) or 0
    by_kind = session.execute(
        select(KnowledgeJob.kind, KnowledgeJob.status, func.count())
        .where(KnowledgeJob.organization_id == organization_id)
        .group_by(KnowledgeJob.kind, KnowledgeJob.status)
    ).all()
    return {
        "queue_depth": len(queued),
        "oldest_queued_age_seconds": oldest_age,
        "failures_last_24h": failures,
        "by_kind_status": [
            {"kind": kind, "status": status, "count": count}
            for kind, status, count in by_kind
        ],
    }


@router.get("/accounts/{organization_id}/health/tests")
def get_health_tests(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """The last 30 runs per kind (retrieval, answer), newest first, for the Health trend."""
    membership_for(organization_id, user, session)
    runs: list[TestRun] = []
    for kind in ("retrieval", "answer"):
        runs.extend(
            session.scalars(
                select(TestRun)
                .where(TestRun.organization_id == organization_id, TestRun.kind == kind)
                .order_by(TestRun.started_at.desc())
                .limit(30)
            ).all()
        )
    runs.sort(key=lambda run: run.started_at, reverse=True)
    return {
        "runs": [
            {
                "id": str(run.id),
                "kind": run.kind,
                "status": run.status,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "git_sha": run.git_sha,
                "prompt_versions": run.prompt_versions,
                "model": run.model,
                "metrics": run.metrics,
            }
            for run in runs
        ]
    }
