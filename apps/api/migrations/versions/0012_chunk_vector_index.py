"""hnsw index for chunk embeddings

Revision ID: 0012
Revises: 0011
"""
from alembic import op


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# m/ef_construction are pgvector's defaults, restated so a later change is a
# visible migration rather than an implicit dependency on the server version.
INDEX_NAME = "ix_chunks_embedding_hnsw"


def upgrade() -> None:
    op.execute(
        f"CREATE INDEX {INDEX_NAME} ON chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX {INDEX_NAME}")
