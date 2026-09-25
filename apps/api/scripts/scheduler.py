"""Scheduler CLI — always runs one tick; --once kept for callers."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_engine  # noqa: E402
from app.scheduler import tick  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Enqueue due schedule rows onto knowledge_jobs.")
    parser.add_argument(
        "--once",
        action="store_true",
        default=True,
        help="Run a single tick and exit (default).",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Ignore --once and tick every 60s.",
    )
    args = parser.parse_args()
    if args.loop:
        import time
        while True:
            with Session(get_engine()) as session:
                print(tick(session), flush=True)
            time.sleep(60)
        return 0
    with Session(get_engine()) as session:
        print(tick(session))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
