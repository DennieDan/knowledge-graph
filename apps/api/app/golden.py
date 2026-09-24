"""Golden acceptance metrics for Health (#102 / F-11).

Until #106 lands a live nightly golden run, Health reads invented fixture
metrics (status ``fixture``). When a live acceptance TestRun or a
``golden_live`` helper is present, status flips to ``live``.

Telemetry never carries PO content, file names, product names or prices —
only aggregate rates and counts.
"""
from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import STACK_TYPES, TestRun

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "golden_metrics.json"


def _load_fixture_file() -> dict[str, Any]:
    if _FIXTURE_PATH.is_file():
        return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    # Minimal fallback if the fixture file is absent.
    return {
        "corpus": "studio-north-precision",
        "question_count": 50,
        "labelled_count": 0,
        "acceptance_mean": 0.0,
        "per_template": {key: {"acceptance": 0.0} for key in STACK_TYPES},
        "note": "Inline fixture fallback; #106 live cut not present.",
    }


def fixture_metrics() -> dict[str, Any]:
    """Invented golden numbers safe to show before the live #106 cut."""
    return _load_fixture_file()


def acceptance_for_template(metrics: dict[str, Any], template_or_stack_key: str) -> float | None:
    per = metrics.get("per_template") or {}
    entry = per.get(template_or_stack_key)
    if not isinstance(entry, dict):
        return None
    value = entry.get("acceptance")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _try_live_module() -> dict[str, Any] | None:
    """Prefer a live helper from #106 when that module is on the tree."""
    try:
        module = import_module("app.golden_live")
    except ImportError:
        return None
    loader = getattr(module, "live_golden_metrics", None)
    if not callable(loader):
        return None
    payload = loader()
    return payload if isinstance(payload, dict) else None


def _try_live_test_run(session: Session, organization_id: UUID) -> dict[str, Any] | None:
    """Use the newest TestRun whose metrics look like a golden/acceptance cut.

    #106 may land as kind ``golden``/``acceptance`` (after a migration) or as a
    retrieval/answer run whose metrics carry ``acceptance_mean`` / ``golden``.
    We accept either so Health can flip to live without waiting on a kind rename.
    """
    runs = session.scalars(
        select(TestRun)
        .where(TestRun.organization_id == organization_id)
        .order_by(TestRun.started_at.desc())
        .limit(30)
    ).all()
    for run in runs:
        metrics = run.metrics if isinstance(run.metrics, dict) else None
        if not metrics:
            continue
        kind_match = run.kind in ("golden", "acceptance")
        shape_match = (
            "acceptance_mean" in metrics
            or metrics.get("golden") is True
            or metrics.get("source") == "golden"
        )
        if not (kind_match or shape_match):
            continue
        payload = dict(metrics)
        payload.setdefault("run_id", str(run.id))
        payload.setdefault("run_status", run.status)
        payload.setdefault("started_at", run.started_at.isoformat())
        return payload
    return None


def golden_panel(session: Session | None = None, organization_id: UUID | None = None) -> dict[str, Any]:
    """Return ``{ status: 'fixture'|'live', metrics: {...} }`` for the Health page."""
    if session is not None and organization_id is not None:
        live_run = _try_live_test_run(session, organization_id)
        if live_run is not None:
            return {"status": "live", "metrics": live_run}
    live_module = _try_live_module()
    if live_module is not None:
        return {"status": "live", "metrics": live_module}
    return {"status": "fixture", "metrics": fixture_metrics()}
