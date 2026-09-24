"""Load apps/api/tests/fixtures/questions.json into test_questions.

Requires migration tables from the maintenance/scoring work (#19). Run after
the sample workspace org exists:

    python -m scripts.load_questions --organization-id <uuid> [--replace]

Chunk/substack ids stay empty until post-ingest labelling. Interview rows
never get invented answers.

Label schema (#106): each synthetic row must carry label_a, label_b, and
agreed. Dual human labels remain outstanding until a teammate completes
label_b and reconcile writes agreed (see docs/golden-labelling.md).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_engine  # noqa: E402
from app.models import TestQuestion  # noqa: E402

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "questions.json"
VERDICTS = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "verdicts.json"

LABEL_STATUSES = frozenset({"outstanding", "done"})


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def _validate_label_side(side: Any, *, field: str, question_id: str) -> None:
    if not isinstance(side, dict):
        raise ValueError(f"{question_id}: {field} must be an object")
    if side.get("status") not in LABEL_STATUSES:
        raise ValueError(f"{question_id}: {field}.status must be outstanding|done")
    quotes = side.get("quotes")
    if not isinstance(quotes, list):
        raise ValueError(f"{question_id}: {field}.quotes must be a list")
    for quote in quotes:
        if not isinstance(quote, dict) or "doc" not in quote or "quote" not in quote:
            raise ValueError(f"{question_id}: {field}.quotes entries need doc + quote")


def validate_fixture(data: dict | None = None) -> dict:
    """Validate label schema and conflict_id references. Raises ValueError on bad rows."""
    data = data or load_fixture()
    verdict_ids = {
        c["id"]
        for c in json.loads(VERDICTS.read_text()).get("planted_conflicts", [])
    }
    for row in data["synthetic"]:
        qid = row["id"]
        for field in ("label_a", "label_b"):
            if field not in row:
                raise ValueError(f"{qid}: missing {field}")
            _validate_label_side(row[field], field=field, question_id=qid)
        if "agreed" not in row:
            raise ValueError(f"{qid}: missing agreed")
        if row["agreed"] is not None and not isinstance(row["agreed"], list):
            raise ValueError(f"{qid}: agreed must be null or a list of {{doc, quote}}")
        if row.get("conflict_id") is not None and row["conflict_id"] not in verdict_ids:
            raise ValueError(f"{qid}: unknown conflict_id {row['conflict_id']}")
        if "held_out" not in row or not isinstance(row["held_out"], bool):
            raise ValueError(f"{qid}: held_out must be a bool")
    return data


def upsert_rows(session: Session, organization_id: UUID, *, replace: bool) -> tuple[int, int]:
    data = validate_fixture()
    if replace:
        session.execute(delete(TestQuestion).where(TestQuestion.organization_id == organization_id))
        session.flush()

    synthetic = 0
    interview = 0
    for row in data["synthetic"] + data.get("from_interview_shapes", data.get("from_interview", [])):
        existing = session.scalar(
            select(TestQuestion).where(
                TestQuestion.organization_id == organization_id,
                TestQuestion.external_key == row["id"],
            )
        )
        payload = {
            "question": row["question"],
            "language": row["language"],
            "origin": row["origin"],
            "answerable": row.get("answerable"),
            "expected_substack_ids": row.get("expected_substack_ids") or [],
            "expected_chunk_ids": row.get("expected_chunk_ids") or [],
            "expected_answer_notes": row.get("expected_answer_notes"),
            "meta": {
                "shape": row.get("shape"),
                "corpus": row.get("corpus"),
                "expected_source_hints": row.get("expected_source_hints") or [],
                "expected_stack_hints": row.get("expected_stack_hints") or [],
                "label_pass": row.get("label_pass"),
                "second_human_label": row.get("second_human_label"),
                "label_a": row.get("label_a"),
                "label_b": row.get("label_b"),
                "agreed": row.get("agreed"),
                "conflict_id": row.get("conflict_id"),
                "held_out": row.get("held_out", False),
                "fixture_id": row["id"],
            },
        }
        if existing is None:
            session.add(
                TestQuestion(
                    organization_id=organization_id,
                    external_key=row["id"],
                    **payload,
                )
            )
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
        if row["origin"] == "synthetic":
            synthetic += 1
        elif row["origin"] == "from_interview":
            interview += 1
        # invented_shape counted neither as synthetic scores nor interview evidence
    session.commit()
    return synthetic, interview


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True, type=UUID)
    parser.add_argument("--replace", action="store_true", help="delete existing rows for this org first")
    parser.add_argument("--validate-only", action="store_true", help="validate fixture and exit")
    args = parser.parse_args()
    if args.validate_only:
        validate_fixture()
        print("OK: questions.json label schema and conflict_ids valid.")
        return 0
    with Session(get_engine()) as session:
        synthetic, interview = upsert_rows(session, args.organization_id, replace=args.replace)
    print(f"Loaded {synthetic} synthetic + {interview} from_interview into org {args.organization_id}")
    print("FLAG: second human label outstanding; chunk ids empty until post-ingest labelling.")
    print("FLAG: interview rows are invented anonymised shapes (transcripts unavailable).")
    print("FLAG: live golden cut not done (#106).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
