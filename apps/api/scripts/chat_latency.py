"""Time local chat turns via the streaming endpoint. Temporary measurement script."""
import json
import statistics
import sys
import time
from base64 import b64encode

import httpx
from itsdangerous import TimestampSigner

sys.path.insert(0, ".")
from app.config import get_settings  # noqa: E402

ORG = "4f9bb588-0ae9-47b5-967a-8575c12b7af0"
USER = "29d68cea-1e0c-4ef1-ac21-7a6d91544734"
API = "http://localhost:8000"
WARMUP = "What orders do we have?"
QUESTIONS = [
    "What did the customer order in PO-5503?",
    "What is the delivery date for PO-5500?",
    "What are the terms of the weekly standing order with 20% flex?",
    "Which client placed PO-5508?",
    "What do we know about the Jasmine rice 25kg sack?",
    "Which clients have ordered prawns?",
    "What contact details do we have for Nguyễn Sông Thương?",
    "Who is Trần Tuấn Kiệt and what have they ordered?",
    "Which sales orders changed quantities after they were placed?",
    "What seafood items do we sell and to whom?",
]

secret = get_settings().session_secret.get_secret_value()
payload = b64encode(json.dumps({"user_id": USER, "organization_id": ORG}).encode())
cookie = TimestampSigner(secret).sign(payload).decode()
client = httpx.Client(base_url=API, cookies={"kg_session": cookie}, timeout=300)
thread = client.post(f"/accounts/{ORG}/chat/threads", json={}).raise_for_status().json()


def ask(question: str) -> dict:
    # Fresh thread per question so history does not grow across the run.
    thread_id = client.post(f"/accounts/{ORG}/chat/threads", json={}).raise_for_status().json()["id"]
    start = time.perf_counter()
    first_event = first_step = None
    model_calls = 0
    final = None
    with client.stream("POST", f"/accounts/{ORG}/chat/threads/{thread_id}/messages/stream", json={"text": question}) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            now = time.perf_counter() - start
            event = json.loads(line)
            first_event = first_event if first_event is not None else now
            if event["type"] == "step" and first_step is None:
                first_step = now
            if event["type"] == "thinking":
                model_calls += 1
            if event["type"] in ("message", "error"):
                final = event
    total = time.perf_counter() - start
    message = (final or {}).get("message") or {}
    return {
        "first_event_s": first_event, "first_step_s": first_step, "total_s": total,
        "model_calls": model_calls, "answered": message.get("answered"), "error": final is None or final["type"] == "error",
    }


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p * (len(ordered) - 1)))]


warm = ask(WARMUP)
print(f"warm-up (not counted): {json.dumps(warm)}")
rows = []
for question in QUESTIONS:
    row = ask(question)
    rows.append(row)
    print(f"{row['first_step_s']:.2f}s first step | {row['total_s']:.2f}s total | "
          f"{row['model_calls']} model calls | answered={row['answered']} error={row['error']}")

ok = [r for r in rows if not r["error"]]
for key in ("first_event_s", "first_step_s", "total_s"):
    values = [r[key] for r in ok if r[key] is not None]
    print(f"{key:14} p50 {statistics.median(values):.2f}s  p95 {pct(values, 0.95):.2f}s  "
          f"min {min(values):.2f}s  max {max(values):.2f}s")
calls = [r["model_calls"] for r in ok]
print(f"model calls avg {statistics.mean(calls):.1f}, max {max(calls)}; "
      f"answered {sum(bool(r['answered']) for r in ok)}/{len(ok)}; errors {len(rows) - len(ok)}")
