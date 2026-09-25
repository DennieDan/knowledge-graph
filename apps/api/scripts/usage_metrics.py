"""Read-only usage, cost, and latency metrics for a Postgres/Supabase database. Makes no changes.

Prints aggregates only (no names, message text, or IDs). Run from apps/api and pass
the target explicitly so local and production never mix:

    DATABASE_URL='postgresql://...pooler.supabase.com:5432/postgres?sslmode=require' \\
        python -m scripts.usage_metrics --days 28

Costs are estimates from recorded token counts and the per-1M-token prices given.
"""
import argparse
import json
import os
import sys

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection

from app.config import psycopg_url
from app.database import set_statement_timeout
from scripts.check_database import connection_error, describe

# USD per 1M tokens (gpt-5-mini, text-embedding-3-small); override with flags.
INPUT_PRICE = 0.25
OUTPUT_PRICE = 2.00
EMBEDDING_PRICE = 0.02
CHARS_PER_TOKEN = 4


def cost(input_tokens: float | None, output_tokens: float | None, input_price: float, output_price: float) -> float:
    return (float(input_tokens or 0) * input_price + float(output_tokens or 0) * output_price) / 1_000_000


def _num(value) -> float | None:
    return None if value is None else round(float(value), 1)


def _row(connection: Connection, sql: str, days: int) -> dict:
    row = connection.execute(text(sql), {"days": days}).mappings().first()
    return {key: _num(value) for key, value in (row or {}).items()}


def _token_stats(
    connection: Connection, table: str, where: str, days: int, input_price: float, output_price: float
) -> dict:
    stats = _row(connection, f"""
        SELECT count(*) AS count,
               avg(input_tokens) AS avg_input, avg(output_tokens) AS avg_output,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY input_tokens) AS p50_input,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY input_tokens) AS p95_input,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY output_tokens) AS p95_output
        FROM {table}
        WHERE {where} AND input_tokens IS NOT NULL AND created_at >= now() - make_interval(days => :days)
    """, days)
    each = cost(stats["avg_input"], stats["avg_output"], input_price, output_price)
    stats["usd_each"] = round(each, 5)
    output_cost = cost(0, stats["avg_output"], input_price, output_price)
    stats["output_share_of_cost"] = round(output_cost / each, 2) if each else None
    return stats


def collect(
    connection: Connection,
    days: int,
    input_price: float = INPUT_PRICE,
    output_price: float = OUTPUT_PRICE,
    embedding_price: float = EMBEDDING_PRICE,
) -> dict:
    metrics: dict = {"window_days": days}
    metrics["generations"] = _token_stats(connection, "generation_runs", "true", days, input_price, output_price)
    metrics["generations_by_prompt"] = [
        {
            "prompt_key": row.prompt_key,
            "model": row.model,
            "count": row.count,
            "avg_input": _num(row.avg_input),
            "avg_output": _num(row.avg_output),
            "usd_each": round(cost(row.avg_input, row.avg_output, input_price, output_price), 5),
        }
        for row in connection.execute(text("""
            SELECT prompt_key, model, count(*) AS count,
                   avg(input_tokens) AS avg_input, avg(output_tokens) AS avg_output
            FROM generation_runs
            WHERE input_tokens IS NOT NULL AND created_at >= now() - make_interval(days => :days)
            GROUP BY prompt_key, model ORDER BY count(*) DESC
        """), {"days": days})
    ]
    # Question and answer rows are written in one transaction, so chat latency is not
    # recoverable here; the scorer section below carries measured answer latency.
    metrics["chat"] = _token_stats(connection, "chat_messages", "role = 'assistant'", days, input_price, output_price)

    spend = _row(connection, """
        SELECT coalesce(sum(input_tokens), 0) AS input_tokens, coalesce(sum(output_tokens), 0) AS output_tokens,
               count(DISTINCT day) AS active_days
        FROM spend WHERE day >= current_date - :days
    """, days)
    spend["usd_total"] = round(cost(spend["input_tokens"], spend["output_tokens"], input_price, output_price), 4)
    spend["usd_per_month_estimate"] = round(spend["usd_total"] / days * 30, 4) if days else None
    metrics["spend"] = spend

    metrics["analysis_runs"] = _row(connection, """
        SELECT count(*) AS count,
               count(*) FILTER (WHERE status = 'failed') AS failed,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY seconds) AS p50_duration_s,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY seconds) AS p95_duration_s,
               avg(seconds / nullif(documents_processed, 0)) AS avg_s_per_document
        FROM (
            SELECT status, documents_processed, extract(epoch FROM completed_at - started_at) AS seconds
            FROM analysis_runs WHERE created_at >= now() - make_interval(days => :days)
        ) runs
    """, days)
    metrics["jobs"] = [
        {"kind": row.kind, "status": row.status, "count": row.count}
        for row in connection.execute(text("""
            SELECT kind, status, count(*) AS count FROM knowledge_jobs
            WHERE created_at >= now() - make_interval(days => :days)
            GROUP BY kind, status ORDER BY kind, status
        """), {"days": days})
    ]

    corpus = _row(connection, """
        SELECT count(*) AS chunks, coalesce(sum(length(text)), 0) AS chars,
               count(*) FILTER (WHERE embedding IS NOT NULL) AS embedded
        FROM chunks
    """, days)
    corpus["estimated_tokens"] = round(corpus["chars"] / CHARS_PER_TOKEN)
    corpus["embedding_api_usd_equivalent"] = round(corpus["estimated_tokens"] * embedding_price / 1_000_000, 4)
    metrics["corpus"] = corpus

    metrics["scorer"] = _row(connection, """
        SELECT count(*) AS results,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY r.latency_ms) AS p50_latency_ms,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY r.latency_ms) AS p95_latency_ms,
               avg(r.recall_at_5) AS recall_at_5, avg(r.recall_at_20) AS recall_at_20,
               avg(r.answered::int) AS answered_rate
        FROM test_results r JOIN test_runs t ON t.id = r.run_id
        WHERE t.started_at >= now() - make_interval(days => :days)
    """, days)
    return metrics


def print_report(metrics: dict) -> None:
    for section, value in metrics.items():
        if isinstance(value, dict):
            print(f"\n{section}")
            for key, item in value.items():
                print(f"  {key:30} {item}")
        elif isinstance(value, list):
            print(f"\n{section}")
            for item in value:
                print("  " + "  ".join(f"{key}={val}" for key, val in item.items()))
        else:
            print(f"{section}: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--input-price", type=float, default=INPUT_PRICE)
    parser.add_argument("--output-price", type=float, default=OUTPUT_PRICE)
    parser.add_argument("--embedding-price", type=float, default=EMBEDDING_PRICE)
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    arguments = parser.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("Set DATABASE_URL explicitly for the database to read.", file=sys.stderr)
        return 2
    url = psycopg_url(url)
    print(f"database: {describe(url)}", file=sys.stderr)
    engine = create_engine(url, connect_args={"connect_timeout": 10})
    event.listen(engine, "connect", set_statement_timeout)
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            metrics = collect(
                connection, arguments.days, arguments.input_price, arguments.output_price, arguments.embedding_price
            )
            connection.rollback()
    except Exception as error:
        print(f"cannot read metrics: {connection_error(error, url)}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    if arguments.json:
        print(json.dumps(metrics, indent=2, default=str))
    else:
        print_report(metrics)
    return 0


if __name__ == "__main__":
    sys.exit(main())
