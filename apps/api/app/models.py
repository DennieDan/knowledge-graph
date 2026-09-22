from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIMENSIONS = 384
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GoogleIdentity(Base):
    __tablename__ = "google_identities"
    __table_args__ = (UniqueConstraint("user_id"), Index("ix_google_identities_user_id", "user_id", unique=True))
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    hosted_domain: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class GoogleAccount(Base):
    __tablename__ = "google_accounts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    scopes: Mapped[str] = mapped_column(Text)
    access_token: Mapped[Optional[str]] = mapped_column(Text)
    access_token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    refresh_token: Mapped[Optional[str]] = mapped_column(Text)
    share_all: Mapped[Optional[bool]] = mapped_column(Boolean)
    shared_file_ids: Mapped[Optional[list]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("account_type IN ('personal','company')", name="valid_account_type"),
        CheckConstraint("account_type = 'personal' OR google_domain IS NOT NULL", name="company_has_google_domain"),
        Index("uq_company_google_domain", "google_domain", unique=True, postgresql_where=text("account_type = 'company'")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    account_type: Mapped[str] = mapped_column(String(20), default="personal")
    google_domain: Mapped[Optional[str]] = mapped_column(String(255))
    created_by_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        CheckConstraint("role IN ('admin','member')", name="valid_membership_role"),
        Index("uq_company_admin", "organization_id", unique=True, postgresql_where=text("role = 'admin'")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", "status"),
        CheckConstraint("status IN ('pending','accepted','revoked','expired')", name="valid_invitation_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    invited_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DriveConnection(Base):
    __tablename__ = "drive_connections"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    google_identity_id: Mapped[UUID] = mapped_column(ForeignKey("google_identities.id", ondelete="CASCADE"))
    scopes: Mapped[str] = mapped_column(Text)
    access_token: Mapped[Optional[str]] = mapped_column(Text)
    access_token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    refresh_token: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="connected")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DriveWorkspace(Base):
    __tablename__ = "drive_workspaces"
    __table_args__ = (
        UniqueConstraint("organization_id", "kind", "google_drive_id", "owner_user_id"),
        CheckConstraint("kind IN ('my_drive','shared_drive')", name="valid_drive_workspace_kind"),
        Index("uq_shared_drive_workspace", "organization_id", "google_drive_id", unique=True, postgresql_where=text("kind = 'shared_drive'")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    google_drive_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    owner_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DriveWorkspaceConnection(Base):
    __tablename__ = "drive_workspace_connections"
    __table_args__ = (UniqueConstraint("workspace_id", "connection_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("drive_workspaces.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[UUID] = mapped_column(ForeignKey("drive_connections.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DriveSelection(Base):
    __tablename__ = "drive_selections"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("drive_workspaces.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    share_all: Mapped[bool] = mapped_column(Boolean, default=False)
    selected_file_ids: Mapped[list] = mapped_column(JSONB, default=list)
    configured: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DriveFile(Base):
    __tablename__ = "drive_files"
    __table_args__ = (UniqueConstraint("workspace_id", "file_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("drive_workspaces.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(Text)
    parents: Mapped[list] = mapped_column(JSONB, default=list)
    modified_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    md5_checksum: Mapped[Optional[str]] = mapped_column(String(64))
    web_view_link: Mapped[Optional[str]] = mapped_column(Text)
    trashed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ingested_modified_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class WhatsappConnection(Base):
    __tablename__ = "whatsapp_connections"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    waha_session: Mapped[str] = mapped_column(String(255), unique=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="STARTING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WhatsappChat(Base):
    __tablename__ = "whatsapp_chats"
    __table_args__ = (
        UniqueConstraint("connection_id", "chat_jid"),
        CheckConstraint("import_status IN ('none','importing','imported','failed')", name="valid_import_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    connection_id: Mapped[UUID] = mapped_column(ForeignKey("whatsapp_connections.id", ondelete="CASCADE"), index=True)
    chat_jid: Mapped[str] = mapped_column(Text)
    name: Mapped[Optional[str]] = mapped_column(Text)
    chat_type: Mapped[str] = mapped_column(String(32), default="contact")
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    organization_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    pending_ingest: Mapped[bool] = mapped_column(Boolean, default=False)
    import_status: Mapped[str] = mapped_column(String(20), default="none")
    import_error: Mapped[Optional[str]] = mapped_column(Text)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WhatsappMessage(Base):
    __tablename__ = "whatsapp_messages"
    __table_args__ = (UniqueConstraint("chat_id", "wa_message_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    chat_id: Mapped[UUID] = mapped_column(ForeignKey("whatsapp_chats.id", ondelete="CASCADE"), index=True)
    wa_message_id: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sender_jid: Mapped[Optional[str]] = mapped_column(Text)
    sender_name: Mapped[Optional[str]] = mapped_column(Text)
    from_me: Mapped[bool] = mapped_column(Boolean, default=False)
    msg_type: Mapped[str] = mapped_column(String(50), default="chat")
    body: Mapped[Optional[str]] = mapped_column(Text)
    has_media: Mapped[bool] = mapped_column(Boolean, default=False)
    raw: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("organization_id", "source", "external_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    drive_workspace_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("drive_workspaces.id", ondelete="SET NULL"), index=True)
    owner_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100))
    external_id: Mapped[Optional[str]] = mapped_column(Text)
    source_uri: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "revision"),
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="sha256_content_hash"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_version_id", "position"),
        CheckConstraint("position >= 0", name="nonnegative_position"),
        CheckConstraint("(embedding IS NULL) = (embedding_model IS NULL)", name="embedding_has_model"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_version_id: Mapped[UUID] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    embedding_model: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
