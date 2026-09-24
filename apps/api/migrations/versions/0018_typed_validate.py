"""current_values view + capped searchable generated columns (#97 Steps 2–3)

Revision ID: 0018
Revises: 0017

Additive only. Claims already have typed value_* columns (0016). This migration:
- creates current_values so UI paths never self-join the claims version table
- promotes a capped allowlist of searchable text keys onto records as generated
  columns (from attributes) with indexes — planner-friendly filter paths
"""
from alembic import op


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

# Keep in sync with app.typed_values.PROMOTED_SEARCHABLE_KEYS (cap = 8).
PROMOTED_SEARCHABLE_KEYS = (
    "order_number",
    "company_name",
    "sku",
    "invoice_number",
    "po_number",
    "job_number",
    "drawing_number",
    "file_name",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE VIEW current_values AS
        SELECT DISTINCT ON (record_id, field_key) *
        FROM claims
        WHERE retracted_at IS NULL
        ORDER BY record_id, field_key, asserted_at DESC
        """
    )

    for key in PROMOTED_SEARCHABLE_KEYS:
        # Generated from attributes JSON — promotes hot filter keys only (capped).
        op.execute(
            f"""
            ALTER TABLE records
            ADD COLUMN {key} text
            GENERATED ALWAYS AS (attributes->>'{key}') STORED
            """
        )
        op.execute(
            f"CREATE INDEX ix_records_{key} ON records ({key})"
        )


def downgrade() -> None:
    for key in reversed(PROMOTED_SEARCHABLE_KEYS):
        op.execute(f"DROP INDEX IF EXISTS ix_records_{key}")
        op.execute(f"ALTER TABLE records DROP COLUMN IF EXISTS {key}")
    op.execute("DROP VIEW IF EXISTS current_values")
