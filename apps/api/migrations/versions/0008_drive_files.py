"""drive file tracking

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drive_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("parents", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("modified_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("md5_checksum", sa.String(length=64), nullable=True),
        sa.Column("web_view_link", sa.Text(), nullable=True),
        sa.Column("trashed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ingested_modified_time", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["drive_workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "file_id"),
    )
    op.create_index("ix_drive_files_workspace_id", "drive_files", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_drive_files_workspace_id", table_name="drive_files")
    op.drop_table("drive_files")
