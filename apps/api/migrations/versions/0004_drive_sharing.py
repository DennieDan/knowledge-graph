"""per-user drive file/folder sharing selection

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('google_accounts', sa.Column('share_all', sa.Boolean(), nullable=True))
    op.add_column('google_accounts', sa.Column('shared_file_ids', JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('google_accounts', 'shared_file_ids')
    op.drop_column('google_accounts', 'share_all')
