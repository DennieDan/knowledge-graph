"""user-scoped whatsapp connections, chats and messages

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('whatsapp_connections',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('waha_session', sa.String(length=255), nullable=False),
    sa.Column('phone_number', sa.String(length=32), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('waha_session')
    )
    op.create_index(op.f('ix_whatsapp_connections_user_id'), 'whatsapp_connections', ['user_id'], unique=True)
    op.create_table('whatsapp_chats',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('connection_id', sa.Uuid(), nullable=False),
    sa.Column('chat_jid', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('chat_type', sa.String(length=32), nullable=False),
    sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('import_status', sa.String(length=20), nullable=False),
    sa.Column('import_error', sa.Text(), nullable=True),
    sa.Column('message_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("import_status IN ('none','importing','imported','failed')", name='valid_import_status'),
    sa.ForeignKeyConstraint(['connection_id'], ['whatsapp_connections.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('connection_id', 'chat_jid')
    )
    op.create_index(op.f('ix_whatsapp_chats_connection_id'), 'whatsapp_chats', ['connection_id'], unique=False)
    op.create_table('whatsapp_messages',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('chat_id', sa.Uuid(), nullable=False),
    sa.Column('wa_message_id', sa.Text(), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('sender_jid', sa.Text(), nullable=True),
    sa.Column('sender_name', sa.Text(), nullable=True),
    sa.Column('from_me', sa.Boolean(), nullable=False),
    sa.Column('msg_type', sa.String(length=50), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('has_media', sa.Boolean(), nullable=False),
    sa.Column('raw', JSONB(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['chat_id'], ['whatsapp_chats.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('chat_id', 'wa_message_id')
    )
    op.create_index(op.f('ix_whatsapp_messages_chat_id'), 'whatsapp_messages', ['chat_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_whatsapp_messages_chat_id'), table_name='whatsapp_messages')
    op.drop_table('whatsapp_messages')
    op.drop_index(op.f('ix_whatsapp_chats_connection_id'), table_name='whatsapp_chats')
    op.drop_table('whatsapp_chats')
    op.drop_index(op.f('ix_whatsapp_connections_user_id'), table_name='whatsapp_connections')
    op.drop_table('whatsapp_connections')
