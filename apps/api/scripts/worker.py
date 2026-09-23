import argparse
import signal
import sys
import time
from uuid import uuid4

from app.worker import run_one

stopping = False


def _request_stop(signum, frame) -> None:
    # Finish the current job, then exit; an interrupted job is reclaimed after its lease.
    global stopping
    stopping = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    arguments = parser.parse_args()
    signal.signal(signal.SIGTERM, _request_stop)
    worker_id = f"worker-{uuid4()}"
    while not stopping:
        worked = run_one(worker_id)
        if arguments.once:
            return 0
        if not worked and not stopping:
            time.sleep(arguments.poll_seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
