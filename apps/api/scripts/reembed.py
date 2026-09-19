"""Backfill chunk embeddings so every stored vector comes from the configured model.

Run from apps/api with the virtual environment active:

    python -m scripts.reembed [--batch-size 64] [--dry-run]
"""
import argparse
import sys

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.ingest import embed_chunks
from app.models import Chunk


def stale_chunks(session: Session, model: str, limit: int) -> list[Chunk]:
    statement = select(Chunk).where(or_(Chunk.embedding_model.is_(None), Chunk.embedding_model != model)).order_by(Chunk.created_at).limit(limit)
    return list(session.scalars(statement))


def reembed(batch_size: int, dry_run: bool) -> int:
    model = get_settings().embedding_model
    total = 0
    with Session(get_engine()) as session:
        pending = session.scalar(select(func.count(Chunk.id)).where(or_(Chunk.embedding_model.is_(None), Chunk.embedding_model != model)))
        print(f"{pending} chunk(s) not embedded with {model}")
        if dry_run:
            return pending
        while True:
            batch = stale_chunks(session, model, batch_size)
            if not batch:
                break
            embed_chunks(batch)
            session.commit()
            total += len(batch)
            print(f"embedded {total}/{pending}", flush=True)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--dry-run", action="store_true", help="report how many chunks need re-embedding and exit")
    arguments = parser.parse_args()
    reembed(arguments.batch_size, arguments.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
