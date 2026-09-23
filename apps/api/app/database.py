from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .config import get_settings

STATEMENT_TIMEOUT_MS = 5000


@lru_cache
def get_engine() -> Engine:
    engine = create_engine(
        get_settings().runtime_url(),
        pool_pre_ping=True,
        pool_timeout=5,
        connect_args={"connect_timeout": 3},
    )
    # Supabase's pooler ignores most startup `options`, so set the timeout per session.
    event.listen(engine, "connect", set_statement_timeout)
    return engine


def set_statement_timeout(dbapi_connection, connection_record) -> None:
    with dbapi_connection.cursor() as cursor:
        cursor.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
    dbapi_connection.commit()


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
