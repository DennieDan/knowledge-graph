"""entity mentions: discover suppliers, supplier orders, and meetings

Revision ID: 0017
Revises: 0016
"""
from alembic import op


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

PREVIOUS = ("sales-orders", "clients", "items")
ENTITY_TYPES = (*PREVIOUS, "suppliers", "supplier-orders", "meetings")


def _replace(types: tuple[str, ...]) -> None:
    op.drop_constraint("valid_entity_mention_type", "entity_mentions", type_="check")
    op.create_check_constraint(
        "valid_entity_mention_type", "entity_mentions", "entity_type IN (" + ",".join(f"'{t}'" for t in types) + ")"
    )


def upgrade() -> None:
    _replace(ENTITY_TYPES)


def downgrade() -> None:
    _replace(PREVIOUS)
