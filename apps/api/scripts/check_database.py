"""Read-only readiness check for a Postgres/Supabase database. Makes no changes.

Run from apps/api. Pass the target explicitly so local and production never mix:

    DATABASE_URL='postgresql://...pooler.supabase.com:5432/postgres?sslmode=require' \\
        python -m scripts.check_database

Add --require-migrated to fail when migrations are pending (e.g. after a deploy).
"""
import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, make_url

from app.config import psycopg_url
from app.database import STATEMENT_TIMEOUT_MS, set_statement_timeout
from app.models import Base

API_ROOT = Path(__file__).resolve().parents[1]
DATA_API_ROLES = ("anon", "authenticated")


@dataclass
class Report:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def ok(self, message: str) -> None:
        print(f"  ok    {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"  warn  {message}")

    def fail(self, message: str) -> None:
        self.failures.append(message)
        print(f"  FAIL  {message}")


def describe(url: str) -> str:
    parsed = make_url(url)
    return f"{parsed.username}@{parsed.host}:{parsed.port or 5432}/{parsed.database}"


def connection_error(error: Exception, url: str) -> str:
    """The driver's first message line, with the password redacted."""
    detail = str(getattr(error, "orig", None) or error).strip().splitlines()
    message = f"{type(error).__name__}: {detail[0] if detail else ''}"
    password = make_url(url).password
    return message.replace(password, "***") if password else message


def alembic_head() -> str | None:
    return ScriptDirectory.from_config(Config(str(API_ROOT / "alembic.ini"))).get_current_head()


def check_runtime(connection: Connection, report: Report, require_migrated: bool) -> None:
    driver = connection.connection.driver_connection
    if driver.pgconn.ssl_in_use:
        report.ok("TLS in use")
    elif driver.info.host in ("localhost", "127.0.0.1", "::1"):
        report.ok("TLS not used (local database)")
    else:
        report.fail("TLS not in use; add ?sslmode=require to the URL")

    report.ok(connection.scalar(text("SELECT version()")).split(",")[0])

    timeout = connection.scalar(text("SHOW statement_timeout"))
    expected = f"{STATEMENT_TIMEOUT_MS // 1000}s"
    if timeout == expected:
        report.ok(f"statement_timeout applied ({timeout})")
    else:
        report.fail(f"statement_timeout is {timeout}, expected {expected}")

    vector = connection.execute(text(
        "SELECT e.extversion, n.nspname FROM pg_extension e "
        "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'vector'"
    )).first()
    if vector is None:
        report.warn("pgvector not installed yet; the first migration creates it")
    elif connection.scalar(text("SELECT to_regtype('vector') IS NOT NULL")):
        report.ok(f"pgvector {vector.extversion} in schema '{vector.nspname}', resolvable on search_path")
    else:
        report.fail(f"pgvector is in schema '{vector.nspname}', which is not on search_path")

    head = alembic_head()
    has_version_table = connection.scalar(text("SELECT to_regclass('alembic_version') IS NOT NULL"))
    current = connection.scalar(text("SELECT version_num FROM alembic_version")) if has_version_table else None
    if current == head:
        report.ok(f"migrations at head ({head})")
    else:
        message = f"migrations pending: database at {current or 'none'}, code head {head}"
        if require_migrated:
            report.fail(message)
        else:
            report.warn(message)

    existing_roles = set(connection.scalars(
        text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"), {"roles": list(DATA_API_ROLES)}
    ))
    tables = [table.name for table in Base.metadata.sorted_tables]
    exposed = sorted({
        f"{role}:{table}"
        for role in existing_roles
        for table in tables
        if connection.scalar(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{table}"})
        and connection.scalar(text("SELECT has_table_privilege(:r, :t, 'SELECT')"), {"r": role, "t": f"public.{table}"})
    })
    if not existing_roles:
        report.ok("no Supabase Data API roles (not a Supabase database)")
    elif exposed:
        report.warn(
            f"{len(exposed)} app table grant(s) to Data API roles (e.g. {exposed[0]}); "
            "keep the Data API disabled or revoke these grants"
        )
    else:
        report.ok("app tables are not granted to Data API roles")


def connect_and_check(label: str, url: str, report: Report, *, runtime: bool, require_migrated: bool) -> None:
    url = psycopg_url(url)
    print(f"{label}: {describe(url)}")
    engine = create_engine(url, connect_args={"connect_timeout": 10})
    if runtime:
        event.listen(engine, "connect", set_statement_timeout)
    try:
        with engine.connect() as connection:
            if runtime:
                check_runtime(connection, report, require_migrated)
            else:
                report.ok("connected")
    except Exception as error:
        report.fail(f"cannot connect: {connection_error(error, url)}")
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--require-migrated", action="store_true")
    arguments = parser.parse_args()

    runtime_url = os.environ.get("DATABASE_URL")
    if not runtime_url:
        print("Set DATABASE_URL explicitly for the database to check.", file=sys.stderr)
        return 2
    report = Report()
    connect_and_check("runtime", runtime_url, report, runtime=True, require_migrated=arguments.require_migrated)
    migration_url = os.environ.get("MIGRATION_DATABASE_URL")
    if migration_url and migration_url != runtime_url:
        connect_and_check("migration", migration_url, report, runtime=False, require_migrated=False)

    print(f"\n{len(report.failures)} failure(s), {len(report.warnings)} warning(s)")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
