"""records, claims, record_links, change_events, order_events (#93 Step 1)

Revision ID: 0016
Revises: 0015

Additive only. Findings already exist on main (0015 / #15); this migration
does not recreate or alter findings — claims.finding_id is a nullable FK
onto the existing table. Stacks catalogue rows (#97) are out of scope here;
records.stack_key is a free string (e.g. sales-orders) until that lands.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


CLAIM_STATUSES = ("proposed", "confirmed", "superseded", "retracted")
CLAIM_VALUE_TYPES = ("text", "numeric", "date", "bool")
ORDER_EVENT_KINDS = (
    "read",
    "proposed",
    "confirmed",
    "edited",
    "replied",
    "rechecked",
    "superseded",
)


def upgrade() -> None:
    op.create_table(
        "records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("stack_key", sa.String(length=80), nullable=False),
        sa.Column("parent_record_id", sa.Uuid(), nullable=True),
        sa.Column("match_key", sa.String(length=255), nullable=True),
        sa.Column("substack_id", sa.Uuid(), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_record_id"], ["records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["substack_id"], ["substacks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_records_organization_id", "records", ["organization_id"])
    op.create_index("ix_records_parent_record_id", "records", ["parent_record_id"])
    op.create_index("ix_records_substack_id", "records", ["substack_id"])
    op.create_index(
        "ix_records_org_stack_match",
        "records",
        ["organization_id", "stack_key", "match_key"],
    )

    op.create_table(
        "claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("field_key", sa.String(length=120), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_numeric", sa.Numeric(), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("value_bool", sa.Boolean(), nullable=True),
        sa.Column("value_type", sa.String(length=20), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("location", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("origin", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="proposed", nullable=False),
        sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("asserted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("retracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visible_via_user_id", sa.Uuid(), nullable=True),
        sa.Column("finding_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN (" + ",".join(f"'{s}'" for s in CLAIM_STATUSES) + ")",
            name="valid_claim_status",
        ),
        sa.CheckConstraint(
            "value_type IN (" + ",".join(f"'{t}'" for t in CLAIM_VALUE_TYPES) + ")",
            name="valid_claim_value_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["record_id"], ["records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["visible_via_user_id"], ["users.id"], ondelete="SET NULL"),
        # Existing findings table from 0015 — enhance, never delete.
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claims_organization_id", "claims", ["organization_id"])
    op.create_index("ix_claims_record_id", "claims", ["record_id"])
    op.create_index("ix_claims_finding_id", "claims", ["finding_id"])
    op.create_index("ix_claims_visible_via_user_id", "claims", ["visible_via_user_id"])
    op.create_index(
        "ix_claims_record_field_status",
        "claims",
        ["record_id", "field_key", "status"],
    )

    # PRD name: links. Table name record_links to avoid colliding with Python builtins
    # and to leave room for other link tables (e.g. substack_links).
    op.create_table(
        "record_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("from_kind", sa.String(length=50), nullable=False),
        sa.Column("from_id", sa.Uuid(), nullable=False),
        sa.Column("to_kind", sa.String(length=50), nullable=False),
        sa.Column("to_id", sa.Uuid(), nullable=False),
        sa.Column("relation_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_record_links_organization_id", "record_links", ["organization_id"])
    op.create_index(
        "ix_record_links_from",
        "record_links",
        ["organization_id", "from_kind", "from_id"],
    )
    op.create_index(
        "ix_record_links_to",
        "record_links",
        ["organization_id", "to_kind", "to_id"],
    )

    op.create_table(
        "change_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("caused_by_finding_id", sa.Uuid(), nullable=True),
        sa.Column("caused_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("change_kind", sa.String(length=80), nullable=False),
        sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reverts_change_event_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["caused_by_finding_id"], ["findings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["caused_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reverts_change_event_id"], ["change_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "sequence_no", name="uq_change_events_org_sequence"),
    )
    op.create_index("ix_change_events_organization_id", "change_events", ["organization_id"])
    op.create_index("ix_change_events_caused_by_finding_id", "change_events", ["caused_by_finding_id"])

    op.create_table(
        "order_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN (" + ",".join(f"'{k}'" for k in ORDER_EVENT_KINDS) + ")",
            name="valid_order_event_kind",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_events_organization_id", "order_events", ["organization_id"])
    op.create_index("ix_order_events_order_at", "order_events", ["order_id", "at"])
    op.create_index("ix_order_events_actor_user_id", "order_events", ["actor_user_id"])


def downgrade() -> None:
    op.drop_index("ix_order_events_actor_user_id", table_name="order_events")
    op.drop_index("ix_order_events_order_at", table_name="order_events")
    op.drop_index("ix_order_events_organization_id", table_name="order_events")
    op.drop_table("order_events")

    op.drop_index("ix_change_events_caused_by_finding_id", table_name="change_events")
    op.drop_index("ix_change_events_organization_id", table_name="change_events")
    op.drop_table("change_events")

    op.drop_index("ix_record_links_to", table_name="record_links")
    op.drop_index("ix_record_links_from", table_name="record_links")
    op.drop_index("ix_record_links_organization_id", table_name="record_links")
    op.drop_table("record_links")

    op.drop_index("ix_claims_record_field_status", table_name="claims")
    op.drop_index("ix_claims_visible_via_user_id", table_name="claims")
    op.drop_index("ix_claims_finding_id", table_name="claims")
    op.drop_index("ix_claims_record_id", table_name="claims")
    op.drop_index("ix_claims_organization_id", table_name="claims")
    op.drop_table("claims")

    op.drop_index("ix_records_org_stack_match", table_name="records")
    op.drop_index("ix_records_substack_id", table_name="records")
    op.drop_index("ix_records_parent_record_id", table_name="records")
    op.drop_index("ix_records_organization_id", table_name="records")
    op.drop_table("records")
