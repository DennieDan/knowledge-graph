import argparse
import sys
import time
from uuid import uuid4

from app.worker import run_one


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    arguments = parser.parse_args()
    worker_id = f"worker-{uuid4()}"
    while True:
        worked = run_one(worker_id)
        if arguments.once:
            return 0
        if not worked:
            time.sleep(arguments.poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
