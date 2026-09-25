from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text, Numeric
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
    daily_token_budget: Mapped[int] = mapped_column(Integer, default=500_000)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        # Dual vocabulary (#101 vs #9): keep admin|member; add owner|sales|planner|supervisor.
        CheckConstraint(
            "role IN ('admin','member','owner','sales','planner','supervisor')",
            name="valid_membership_role",
        ),
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
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
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
        CheckConstraint("origin IN ('waha','export')", name="valid_chat_origin"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    connection_id: Mapped[UUID] = mapped_column(ForeignKey("whatsapp_connections.id", ondelete="CASCADE"), index=True)
    chat_jid: Mapped[str] = mapped_column(Text)
    name: Mapped[Optional[str]] = mapped_column(Text)
    chat_type: Mapped[str] = mapped_column(String(32), default="contact")
    origin: Mapped[str] = mapped_column(String(16), default="waha", server_default="waha")
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    organization_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    pending_ingest: Mapped[bool] = mapped_column(Boolean, default=False)
    import_status: Mapped[str] = mapped_column(String(20), default="none")
    import_error: Mapped[Optional[str]] = mapped_column(Text)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
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
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_version_id: Mapped[UUID] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    embedding_model: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


STACK_TYPES = (
    "sales-orders", "clients", "items", "invoices", "suppliers",
    "supplier-orders", "production-jobs", "specifications",
    "conversations", "pics", "meetings", "files",
)
# Hidden from the product; the substacks check still allows them until a later contract migration.
RETIRED_STACK_TYPES = ("invoices", "production-jobs", "pics")
ACTIVE_STACK_TYPES = tuple(t for t in STACK_TYPES if t not in RETIRED_STACK_TYPES)
ENTITY_TYPES = ("sales-orders", "clients", "items", "suppliers", "supplier-orders", "meetings")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint("trigger IN ('ingest','manual','retry','backfill')", name="valid_analysis_trigger"),
        CheckConstraint("status IN ('queued','embedding','discovering','generating','completed','partial','failed')", name="valid_analysis_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trigger: Mapped[str] = mapped_column(String(20), default="ingest")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    documents_total: Mapped[int] = mapped_column(Integer, default=0)
    documents_processed: Mapped[int] = mapped_column(Integer, default=0)
    chunks_embedded: Mapped[int] = mapped_column(Integer, default=0)
    candidates_found: Mapped[int] = mapped_column(Integer, default=0)
    substacks_created: Mapped[int] = mapped_column(Integer, default=0)
    substacks_updated: Mapped[int] = mapped_column(Integer, default=0)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[Optional[str]] = mapped_column(Text)
    input_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    config_version: Mapped[str] = mapped_column(String(50), default="core-v1")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeJob(Base):
    __tablename__ = "knowledge_jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('embed_version','discover_document','generate_substack','reconcile_scope','run_checks','sync_workspace','whatsapp_ingest','score_questions','run_recheck','propose_version')", name="valid_knowledge_job_kind"),
        CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled','budget_exhausted')", name="valid_knowledge_job_status"),
        Index("ix_knowledge_jobs_available", "status", "available_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    analysis_run_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=4)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[Optional[str]] = mapped_column(String(255))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Substack(Base):
    __tablename__ = "substacks"
    __table_args__ = (
        CheckConstraint("stack_type IN (" + ",".join(f"'{t}'" for t in STACK_TYPES) + ")", name="valid_stack_type"),
        CheckConstraint("status IN ('proposed','confirmed')", name="valid_substack_status"),
        CheckConstraint("review_state IN ('clean','pending','pending_update','unsupported','generation_error')", name="valid_substack_review_state"),
        CheckConstraint("created_by IN ('system','user')", name="valid_substack_created_by"),
        Index("uq_shared_substack_identity", "organization_id", "stack_type", "identity_key", unique=True, postgresql_where=text("owner_user_id IS NULL AND identity_key IS NOT NULL")),
        Index("uq_private_substack_identity", "organization_id", "owner_user_id", "stack_type", "identity_key", unique=True, postgresql_where=text("owner_user_id IS NOT NULL AND identity_key IS NOT NULL")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    stack_type: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    review_state: Mapped[str] = mapped_column(String(30), default="clean")
    identity_key: Mapped[Optional[str]] = mapped_column(Text)
    identity_kind: Mapped[Optional[str]] = mapped_column(String(50))
    owner_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    last_analysis_run_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"), index=True)
    created_by: Mapped[str] = mapped_column(String(10), default="system")
    created_by_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SubstackSource(Base):
    __tablename__ = "substack_sources"
    __table_args__ = (
        UniqueConstraint("substack_id", "document_id"),
        CheckConstraint("role IN ('evidence','attachment')", name="valid_substack_source_role"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    substack_id: Mapped[UUID] = mapped_column(ForeignKey("substacks.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="evidence")


class EntityMention(Base):
    __tablename__ = "entity_mentions"
    __table_args__ = (
        CheckConstraint("entity_type IN (" + ",".join(f"'{t}'" for t in ENTITY_TYPES) + ")", name="valid_entity_mention_type"),
        CheckConstraint("status IN ('current','superseded')", name="valid_entity_mention_status"),
        UniqueConstraint("document_version_id", "candidate_key"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    document_version_id: Mapped[UUID] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    identity_key: Mapped[Optional[str]] = mapped_column(Text)
    identity_kind: Mapped[Optional[str]] = mapped_column(String(50))
    candidate_key: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSONB)
    cited_chunk_ids: Mapped[list] = mapped_column(JSONB, default=list)
    substack_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("substacks.id", ondelete="SET NULL"), index=True)
    prompt_key: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="current")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SubstackLink(Base):
    __tablename__ = "substack_links"
    __table_args__ = (UniqueConstraint("substack_id", "related_substack_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    substack_id: Mapped[UUID] = mapped_column(ForeignKey("substacks.id", ondelete="CASCADE"), index=True)
    related_substack_id: Mapped[UUID] = mapped_column(ForeignKey("substacks.id", ondelete="CASCADE"), index=True)
    reason: Mapped[Optional[str]] = mapped_column(Text)


class SubstackContent(Base):
    __tablename__ = "substack_contents"
    __table_args__ = (
        UniqueConstraint("substack_id", "revision"),
        CheckConstraint("revision > 0", name="positive_content_revision"),
        CheckConstraint("status IN ('proposed','confirmed','superseded','stale','unsupported')", name="valid_content_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    substack_id: Mapped[UUID] = mapped_column(ForeignKey("substacks.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    prompt_key: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(255))
    content: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    inputs_fingerprint: Mapped[str] = mapped_column(String(64))
    # NULL confirmed_by_user_id on confirmed content means a generator
    # confirmed its own output; no person has checked it.
    confirmed_by_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentCitation(Base):
    __tablename__ = "content_citations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    content_id: Mapped[UUID] = mapped_column(ForeignKey("substack_contents.id", ondelete="CASCADE"), index=True)
    segment_index: Mapped[int] = mapped_column(Integer)
    chunk_id: Mapped[UUID] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"))
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    locator: Mapped[Optional[dict]] = mapped_column(JSONB)


class GenerationRun(Base):
    __tablename__ = "generation_runs"
    __table_args__ = (CheckConstraint("status IN ('ok','error')", name="valid_generation_run_status"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    substack_id: Mapped[UUID] = mapped_column(ForeignKey("substacks.id", ondelete="CASCADE"), index=True)
    prompt_key: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(255))
    input_chunk_ids: Mapped[list] = mapped_column(JSONB, default=list)
    input_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    retrieval_version: Mapped[Optional[str]] = mapped_column(String(50))
    provider_request_id: Mapped[Optional[str]] = mapped_column(String(255))
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(10), default="ok")
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatThread(Base):
    __tablename__ = "chat_threads"
    __table_args__ = (Index("ix_chat_threads_org_user", "organization_id", "user_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    # Threads are private to the person who asked: answers can quote that
    # person's owner-only documents, so they must not be shared org-wide.
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="valid_chat_message_role"),
        CheckConstraint("feedback IN ('up','down')", name="valid_chat_feedback"),
        CheckConstraint("role = 'assistant' OR feedback IS NULL", name="feedback_on_assistant_only"),
        Index("ix_chat_messages_thread_created", "thread_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    thread_id: Mapped[UUID] = mapped_column(ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    # The question actually retrieved on, after follow-ups are rewritten.
    resolved_question: Mapped[Optional[str]] = mapped_column(Text)
    answered: Mapped[Optional[bool]] = mapped_column(Boolean)
    # True only when every citation is a record a person confirmed.
    checked: Mapped[Optional[bool]] = mapped_column(Boolean)
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    steps: Mapped[list] = mapped_column(JSONB, default=list)
    model: Mapped[Optional[str]] = mapped_column(String(255))
    prompt_version: Mapped[Optional[str]] = mapped_column(String(50))
    retrieval_version: Mapped[Optional[str]] = mapped_column(String(50))
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    feedback: Mapped[Optional[str]] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


DISMISSAL_REASONS = (
    "not_a_change",
    "already_handled",
    "source_is_wrong",
    "duplicate",
    "other_recorded_below",
)


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint(
            "decision IS NULL OR decision IN ('dismissed','acted','confirmed')",
            name="valid_finding_decision",
        ),
        CheckConstraint(
            "dismissal_reason IS NULL OR dismissal_reason IN ("
            + ",".join(f"'{r}'" for r in DISMISSAL_REASONS)
            + ")",
            name="valid_finding_dismissal_reason",
        ),
        Index("ix_findings_check_key", "organization_id", "check_key"),
        Index(
            "ix_findings_open",
            "organization_id",
            "detected_at",
            postgresql_where=text("decision IS NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    check_key: Mapped[str] = mapped_column(String(80))
    subject_kind: Mapped[str] = mapped_column(String(50))
    subject_id: Mapped[UUID] = mapped_column()
    observed_value: Mapped[Optional[str]] = mapped_column(Text)
    threshold_value: Mapped[Optional[str]] = mapped_column(Text)
    summary_sentence: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    detector_version: Mapped[str] = mapped_column(String(50), default="checks-v1")
    decision: Mapped[Optional[str]] = mapped_column(String(20))
    decided_by_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dismissal_reason: Mapped[Optional[str]] = mapped_column(String(40))
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True)


class Schedule(Base):
    __tablename__ = "schedules"
    __table_args__ = (
        UniqueConstraint("key", "organization_id", name="uq_schedule_key_org"),
        Index("ix_schedules_next_run", "enabled", "next_run_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(80))
    cron: Mapped[str] = mapped_column(String(80))
    organization_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Spend(Base):
    __tablename__ = "spend"
    __table_args__ = (UniqueConstraint("organization_id", "day", name="uq_spend_org_day"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)


class TestQuestion(Base):
    __tablename__ = "test_questions"
    __table_args__ = (
        CheckConstraint(
            "origin IN ('synthetic','from_interview','invented_shape')",
            name="valid_test_question_origin",
        ),
        CheckConstraint("language IN ('en','ms','zh')", name="valid_test_question_language"),
        UniqueConstraint("organization_id", "external_key", name="uq_test_question_org_key"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    external_key: Mapped[str] = mapped_column(String(80))
    question: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(10), default="en")
    origin: Mapped[str] = mapped_column(String(30))
    expected_substack_ids: Mapped[list] = mapped_column(JSONB, default=list)
    expected_chunk_ids: Mapped[list] = mapped_column(JSONB, default=list)
    expected_answer_notes: Mapped[Optional[str]] = mapped_column(Text)
    answerable: Mapped[Optional[bool]] = mapped_column(Boolean)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TestRun(Base):
    __tablename__ = "test_runs"
    __table_args__ = (
        CheckConstraint("kind IN ('retrieval','answer')", name="valid_test_run_kind"),
        CheckConstraint("status IN ('running','passed','failed','skipped')", name="valid_test_run_status"),
        Index("ix_test_runs_organization_id", "organization_id", "started_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    git_sha: Mapped[Optional[str]] = mapped_column(String(64))
    prompt_versions: Mapped[dict] = mapped_column(JSONB, default=dict)
    model: Mapped[Optional[str]] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="running")
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)


class TestResult(Base):
    __tablename__ = "test_results"
    __table_args__ = (UniqueConstraint("run_id", "question_id", name="uq_test_result_run_question"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"))
    question_id: Mapped[UUID] = mapped_column(ForeignKey("test_questions.id", ondelete="CASCADE"))
    rank_of_first_expected: Mapped[Optional[int]] = mapped_column(Integer)
    recall_at_5: Mapped[Optional[float]] = mapped_column(Float)
    recall_at_20: Mapped[Optional[float]] = mapped_column(Float)
    cited_expected: Mapped[Optional[bool]] = mapped_column(Boolean)
    answered: Mapped[Optional[bool]] = mapped_column(Boolean)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    tokens: Mapped[Optional[int]] = mapped_column(Integer)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)


class ConfirmEvent(Base):
    __tablename__ = "confirm_events"
    __table_args__ = (
        CheckConstraint("kind IN ('person','bulk','auto')", name="valid_confirm_event_kind"),
        Index("ix_confirm_events_at", "organization_id", "at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    substack_id: Mapped[UUID] = mapped_column(ForeignKey("substacks.id", ondelete="CASCADE"))
    content_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("substack_contents.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20))
    by_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Records / claims (#93 Step 1). Findings stay as above; do not replace. ---

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


class Record(Base):
    __tablename__ = "records"
    __table_args__ = (
        Index("ix_records_org_stack_match", "organization_id", "stack_key", "match_key"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    stack_key: Mapped[str] = mapped_column(String(80))
    parent_record_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("records.id", ondelete="SET NULL"), index=True)
    match_key: Mapped[Optional[str]] = mapped_column(String(255))
    # Bridge to existing Substack rows (#44); nullable until a record is linked.
    substack_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("substacks.id", ondelete="SET NULL"), index=True)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ",".join(f"'{s}'" for s in CLAIM_STATUSES) + ")",
            name="valid_claim_status",
        ),
        CheckConstraint(
            "value_type IN (" + ",".join(f"'{t}'" for t in CLAIM_VALUE_TYPES) + ")",
            name="valid_claim_value_type",
        ),
        Index("ix_claims_record_field_status", "record_id", "field_key", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    record_id: Mapped[UUID] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), index=True)
    field_key: Mapped[str] = mapped_column(String(120))
    value_text: Mapped[Optional[str]] = mapped_column(Text)
    value_numeric: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    value_date: Mapped[Optional[date]] = mapped_column(Date)
    value_bool: Mapped[Optional[bool]] = mapped_column(Boolean)
    value_type: Mapped[str] = mapped_column(String(20))
    quote: Mapped[Optional[str]] = mapped_column(Text)
    location: Mapped[Optional[dict]] = mapped_column(JSONB)
    origin: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    confirmed_by_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    asserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    retracted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # WhatsApp chats are user-scoped; confirmed facts stay org-owned but
    # visibility of the source must still honour this user (#93 Step 2).
    visible_via_user_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    finding_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("findings.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecordLink(Base):
    """PRD name: links. Polymorphic edges between records and other kinds."""

    __tablename__ = "record_links"
    __table_args__ = (
        Index("ix_record_links_from", "organization_id", "from_kind", "from_id"),
        Index("ix_record_links_to", "organization_id", "to_kind", "to_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    from_kind: Mapped[str] = mapped_column(String(50))
    from_id: Mapped[UUID] = mapped_column()
    to_kind: Mapped[str] = mapped_column(String(50))
    to_id: Mapped[UUID] = mapped_column()
    relation_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChangeEvent(Base):
    __tablename__ = "change_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "sequence_no", name="uq_change_events_org_sequence"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    sequence_no: Mapped[int] = mapped_column(Integer)
    caused_by_finding_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("findings.id", ondelete="SET NULL"), index=True
    )
    caused_by_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    change_kind: Mapped[str] = mapped_column(String(80))
    before_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    after_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    reverts_change_event_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("change_events.id", ondelete="SET NULL")
    )


class OrderEvent(Base):
    """Append-only order timeline. actor_user_id is required — no anonymous events."""

    __tablename__ = "order_events"
    __table_args__ = (
        CheckConstraint(
            "kind IN (" + ",".join(f"'{k}'" for k in ORDER_EVENT_KINDS) + ")",
            name="valid_order_event_kind",
        ),
        Index("ix_order_events_order_at", "order_id", "at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class Subscription(Base):
    """Push-watch subscription for Drive, Gmail, or Graph (#92).

    Stub until a verified webhook domain is registered. Drive polling in
    drive_sync.py remains the live sync path.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (Index("ix_subscriptions_expires_at", "expires_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40))
    external_channel_id: Mapped[Optional[str]] = mapped_column(String(255))
    resource_id: Mapped[Optional[str]] = mapped_column(String(255))
    cursor: Mapped[Optional[str]] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("drive_connections.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# Industry catalogue (#97). Distinct from Substack, which holds record instances.
STACK_FIELD_VALUE_TYPES = ("text", "numeric", "date", "bool")


class Stack(Base):
    """Per-org stack type in the industry catalogue (not a Substack record)."""

    __tablename__ = "stacks"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_stacks_organization_key"),
        Index("ix_stacks_profile_key", "organization_id", "profile_key"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(Text)
    parent_stack_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("stacks.id", ondelete="SET NULL"), index=True
    )
    profile_key: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StackField(Base):
    """Field definition belonging to a catalogue Stack row."""

    __tablename__ = "stack_fields"
    __table_args__ = (
        UniqueConstraint("stack_id", "key", name="uq_stack_fields_stack_key"),
        CheckConstraint(
            "value_type IN (" + ",".join(f"'{t}'" for t in STACK_FIELD_VALUE_TYPES) + ")",
            name="valid_stack_field_value_type",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    stack_id: Mapped[UUID] = mapped_column(ForeignKey("stacks.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(String(20))
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    meaning: Mapped[Optional[str]] = mapped_column(Text)
    searchable: Mapped[bool] = mapped_column(Boolean, default=False)


# Assistant connector (#94 F-03): one named, revocable key per connected assistant.


class ConnectorKey(Base):
    """A read-only key that lets one AI assistant read the record over MCP.

    The assistant reads with the walls of the person who created the key: their
    company, the private records and chats only they can see, and their role's
    field rules. Only the key's SHA-256 is stored; the key itself is shown once.
    """

    __tablename__ = "connector_keys"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # The key's first characters, so settings can tell keys apart without storing them.
    prefix: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
