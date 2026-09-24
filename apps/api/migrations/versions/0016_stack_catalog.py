"""stack catalogue: stacks + stack_fields (#97 Step 1)

Revision ID: 0016
Revises: 0015

Industry profiles seed rows here; do not confuse with substacks (record instances).
"""
from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


VALUE_TYPES = ("text", "numeric", "date", "bool")


def upgrade() -> None:
    op.create_table(
        "stacks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_stack_id", sa.Uuid(), nullable=True),
        sa.Column("profile_key", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_stack_id"], ["stacks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "key", name="uq_stacks_organization_key"),
    )
    op.create_index("ix_stacks_organization_id", "stacks", ["organization_id"])
    op.create_index("ix_stacks_parent_stack_id", "stacks", ["parent_stack_id"])
    op.create_index("ix_stacks_profile_key", "stacks", ["organization_id", "profile_key"])

    op.create_table(
        "stack_fields",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("stack_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(length=20), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("meaning", sa.Text(), nullable=True),
        sa.Column("searchable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "value_type IN (" + ",".join(f"'{t}'" for t in VALUE_TYPES) + ")",
            name="valid_stack_field_value_type",
        ),
        sa.ForeignKeyConstraint(["stack_id"], ["stacks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stack_id", "key", name="uq_stack_fields_stack_key"),
    )
    op.create_index("ix_stack_fields_stack_id", "stack_fields", ["stack_id"])


def downgrade() -> None:
    op.drop_table("stack_fields")
    op.drop_table("stacks")
