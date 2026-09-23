"""Load apps/api/tests/fixtures/questions.json into test_questions.

Requires migration tables from the maintenance/scoring work (#19). Run after
the sample workspace org exists:

    python -m scripts.load_questions --organization-id <uuid> [--replace]

Chunk/substack ids stay empty until post-ingest labelling. Interview rows
never get invented answers.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_engine  # noqa: E402
from app.models import TestQuestion  # noqa: E402

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "questions.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def upsert_rows(session: Session, organization_id: UUID, *, replace: bool) -> tuple[int, int]:
    data = load_fixture()
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
    args = parser.parse_args()
    with Session(get_engine()) as session:
        synthetic, interview = upsert_rows(session, args.organization_id, replace=args.replace)
    print(f"Loaded {synthetic} synthetic + {interview} from_interview into org {args.organization_id}")
    print("FLAG: second human label outstanding; chunk ids empty until post-ingest labelling.")
    print("FLAG: interview rows are invented anonymised shapes (transcripts unavailable).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
