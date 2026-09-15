from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_timeout=5,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=5000"},
    )


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
