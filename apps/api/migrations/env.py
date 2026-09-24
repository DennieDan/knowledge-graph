from alembic import context
from sqlalchemy import create_engine, pool
from pgvector.sqlalchemy import Vector

from app.config import get_settings
from app.models import Base


def render_item(type_, obj, autogen_context):
    if type_ == "type" and isinstance(obj, Vector):
        return f"Vector({obj.dim!r})"
    return False


def run_migrations() -> None:
    url = get_settings().migration_url()
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=Base.metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(url, poolclass=pool.NullPool, connect_args={"connect_timeout": 10})
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True, render_item=render_item)
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()


run_migrations()
