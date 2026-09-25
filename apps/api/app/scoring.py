"""Nightly question scoring — retrieval first; answer / golden stubs (#72, #106)."""
from __future__ import annotations

import os
import statistics
import subprocess
import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .findings import create_finding
from .golden import fixture_golden_metrics, run_golden
from .models import TestQuestion, TestResult, TestRun
from .retrieval import search_chunks
from .spend import budget_exhausted


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _git_sha() -> str | None:
    env = os.environ.get("GIT_SHA") or os.environ.get("GITHUB_SHA")
    if env:
        return env[:64]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()[:64]
    except (OSError, subprocess.CalledProcessError):
        return None


def _recall(expected: set[str], ranked_ids: list[str], k: int) -> float:
    if not expected:
        return 0.0
    hit = expected.intersection(ranked_ids[:k])
    return len(hit) / len(expected)


def _rank_of_first(expected: set[str], ranked_ids: list[str]) -> int | None:
    for index, chunk_id in enumerate(ranked_ids, start=1):
        if chunk_id in expected:
            return index
    return None


def run_retrieval_score(session: Session, organization_id: UUID) -> TestRun:
    settings = get_settings()
    questions = session.scalars(
        select(TestQuestion).where(
            TestQuestion.organization_id == organization_id,
            TestQuestion.origin.in_(("synthetic", "from_interview")),
        )
    ).all()
    labelled = [q for q in questions if q.expected_chunk_ids]
    run = TestRun(
        organization_id=organization_id,
        kind="retrieval",
        status="running",
        git_sha=_git_sha(),
        prompt_versions={"retrieval": "hybrid-v1"},
        model=settings.embedding_model,
        started_at=utcnow(),
    )
    session.add(run)
    session.flush()

    if not labelled:
        run.status = "skipped"
        run.finished_at = utcnow()
        run.metrics = {
            "reason": "no_labelled_questions",
            "question_count": len(questions),
            "labelled_count": 0,
        }
        session.commit()
        return run

    by_origin: dict[str, list[float]] = {}
    for question in labelled:
        expected = {str(cid) for cid in (question.expected_chunk_ids or [])}
        owner_id = (question.meta or {}).get("owner_user_id")
        owner_uuid = UUID(owner_id) if owner_id else None
        started = time.perf_counter()
        hits = search_chunks(session, organization_id, owner_uuid, question.question, limit=20)
        latency_ms = int((time.perf_counter() - started) * 1000)
        ranked = [str(item.chunk.id) for item in hits]
        recall5 = _recall(expected, ranked, 5)
        recall20 = _recall(expected, ranked, 20)
        rank = _rank_of_first(expected, ranked)
        session.add(
            TestResult(
                run_id=run.id,
                question_id=question.id,
                rank_of_first_expected=rank,
                recall_at_5=recall5,
                recall_at_20=recall20,
                latency_ms=latency_ms,
                detail={"origin": question.origin, "ranked_chunk_ids": ranked[:20]},
            )
        )
        by_origin.setdefault(question.origin, []).append(recall5)

    metrics = {
        "by_origin": {
            origin: {
                "count": len(values),
                "recall_at_5_mean": (sum(values) / len(values)) if values else None,
            }
            for origin, values in by_origin.items()
        },
        "labelled_count": len(labelled),
        "recall_at_5_mean": (
            sum(v for values in by_origin.values() for v in values) / max(1, len(labelled))
        ),
    }
    run.metrics = metrics
    run.finished_at = utcnow()
    failed = _regression_failed(session, organization_id, "retrieval", metrics, exclude_run_id=run.id)
    run.status = "failed" if failed else "passed"
    if failed:
        create_finding(
            session,
            organization_id=organization_id,
            check_key="health_nightly_regression",
            subject_kind="test_run",
            subject_id=run.id,
            summary_sentence="Nightly retrieval score regressed versus the last 7 runs.",
            observed_value=str(metrics.get("recall_at_5_mean")),
            evidence={"metrics": metrics, "run_id": str(run.id)},
        )
    session.commit()
    return run


def run_answer_score(session: Session, organization_id: UUID) -> TestRun:
    """Answer scoring stub: attach golden harness/fixture metrics (#106).

    Live answer scoring against the chat agent still waits on labelled quotes
    and the golden cut; do not treat these metrics as a release gate.
    """
    settings = get_settings()
    golden = run_golden(session, organization_id, held_out=False)
    run = TestRun(
        organization_id=organization_id,
        kind="answer",
        status="skipped",
        git_sha=_git_sha(),
        prompt_versions={},
        model=settings.openai_model,
        started_at=utcnow(),
        finished_at=utcnow(),
        metrics={
            "reason": "live_golden_cut_not_done",
            "stub": True,
            "golden": golden,
            "fixture": fixture_golden_metrics(),
        },
    )
    session.add(run)
    session.commit()
    return run


def _regression_failed(
    session: Session,
    organization_id: UUID,
    kind: str,
    metrics: dict,
    *,
    exclude_run_id: UUID | None = None,
) -> bool:
    query = (
        select(TestRun)
        .where(
            TestRun.organization_id == organization_id,
            TestRun.kind == kind,
            TestRun.status.in_(("passed", "failed")),
            TestRun.finished_at.is_not(None),
        )
        .order_by(TestRun.started_at.desc())
        .limit(8)
    )
    prior = [
        r for r in session.scalars(query).all()
        if exclude_run_id is None or r.id != exclude_run_id
    ][:7]
    baselines = [
        float(r.metrics["recall_at_5_mean"])
        for r in prior
        if isinstance(r.metrics, dict) and r.metrics.get("recall_at_5_mean") is not None
    ]
    current = metrics.get("recall_at_5_mean")
    if current is None or len(baselines) < 2:
        return False
    median = statistics.median(baselines)
    return (median - float(current)) > 0.05


def run_score_job(session: Session, organization_id: UUID) -> dict:
    if budget_exhausted(session, organization_id):
        return {"status": "budget_exhausted"}
    retrieval = run_retrieval_score(session, organization_id)
    answer = run_answer_score(session, organization_id)
    golden = run_golden(session, organization_id, held_out=False)
    return {
        "retrieval_run_id": str(retrieval.id),
        "retrieval_status": retrieval.status,
        "answer_run_id": str(answer.id),
        "answer_status": answer.status,
        "golden": golden,
    }
