"""accounts and drive workspaces

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("account_type", sa.String(length=20), nullable=True))
    op.add_column("organizations", sa.Column("google_domain", sa.String(length=255), nullable=True))
    op.add_column("organizations", sa.Column("created_by_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_organizations_created_by", "organizations", "users", ["created_by_user_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_organizations_created_by_user_id", "organizations", ["created_by_user_id"])
    op.execute("UPDATE organizations SET account_type = 'personal'")
    op.alter_column("organizations", "account_type", nullable=False, server_default="personal")
    op.create_check_constraint("valid_account_type", "organizations", "account_type IN ('personal','company')")
    op.create_check_constraint("company_has_google_domain", "organizations", "account_type = 'personal' OR google_domain IS NOT NULL")

    op.create_table(
        "google_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("google_sub", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hosted_domain", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("google_sub"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_google_identities_user_id", "google_identities", ["user_id"], unique=True)

    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('admin','member')", name="valid_membership_role"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id"),
    )
    op.create_index("ix_organization_memberships_organization_id", "organization_memberships", ["organization_id"])
    op.create_index("ix_organization_memberships_user_id", "organization_memberships", ["user_id"])

    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending','accepted','revoked','expired')", name="valid_invitation_status"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "email", "status"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_organization_invitations_organization_id", "organization_invitations", ["organization_id"])

    op.create_table(
        "drive_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("google_identity_id", sa.Uuid(), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="connected", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["google_identity_id"], ["google_identities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id"),
    )
    op.create_index("ix_drive_connections_organization_id", "drive_connections", ["organization_id"])
    op.create_index("ix_drive_connections_user_id", "drive_connections", ["user_id"])

    op.create_table(
        "drive_workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("google_drive_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('my_drive','shared_drive')", name="valid_drive_workspace_kind"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "kind", "google_drive_id", "owner_user_id"),
    )
    op.create_index("ix_drive_workspaces_organization_id", "drive_workspaces", ["organization_id"])
    op.create_index("ix_drive_workspaces_owner_user_id", "drive_workspaces", ["owner_user_id"])
    op.create_index("uq_shared_drive_workspace", "drive_workspaces", ["organization_id", "google_drive_id"], unique=True, postgresql_where=sa.text("kind = 'shared_drive'"))

    op.create_table(
        "drive_workspace_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["drive_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["drive_workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "connection_id"),
    )
    op.create_index("ix_drive_workspace_connections_workspace_id", "drive_workspace_connections", ["workspace_id"])
    op.create_index("ix_drive_workspace_connections_connection_id", "drive_workspace_connections", ["connection_id"])

    op.create_table(
        "drive_selections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("share_all", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("selected_file_ids", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("configured", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["drive_workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id"),
    )
    op.create_index("ix_drive_selections_workspace_id", "drive_selections", ["workspace_id"])
    op.create_index("ix_drive_selections_user_id", "drive_selections", ["user_id"])

    op.add_column("documents", sa.Column("drive_workspace_id", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("owner_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_documents_drive_workspace", "documents", "drive_workspaces", ["drive_workspace_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_documents_owner_user", "documents", "users", ["owner_user_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_documents_drive_workspace_id", "documents", ["drive_workspace_id"])
    op.create_index("ix_documents_owner_user_id", "documents", ["owner_user_id"])

    op.execute("""
        INSERT INTO google_identities (id, user_id, google_sub, email, created_at, updated_at)
        SELECT gen_random_uuid(), ga.user_id, ga.google_sub, u.email, ga.created_at, ga.updated_at
        FROM google_accounts ga JOIN users u ON u.id = ga.user_id
    """)
    op.execute("""
        INSERT INTO organizations (id, name, account_type, created_by_user_id, created_at)
        SELECT gen_random_uuid(), COALESCE(u.display_name, u.email) || '''s workspace', 'personal', u.id, now()
        FROM users u
        WHERE EXISTS (SELECT 1 FROM google_accounts ga WHERE ga.user_id = u.id)
          AND NOT EXISTS (SELECT 1 FROM organization_memberships om WHERE om.user_id = u.id)
    """)
    op.execute("""
        INSERT INTO organization_memberships (id, organization_id, user_id, role, created_at)
        SELECT gen_random_uuid(), o.id, o.created_by_user_id, 'admin', now()
        FROM organizations o WHERE o.created_by_user_id IS NOT NULL
    """)
    op.execute("""
        INSERT INTO drive_connections (id, organization_id, user_id, google_identity_id, scopes, access_token, access_token_expires_at, refresh_token, status, created_at, updated_at)
        SELECT gen_random_uuid(), o.id, ga.user_id, gi.id, ga.scopes, ga.access_token, ga.access_token_expires_at, ga.refresh_token, 'connected', ga.created_at, ga.updated_at
        FROM google_accounts ga
        JOIN google_identities gi ON gi.user_id = ga.user_id
        JOIN organizations o ON o.created_by_user_id = ga.user_id
    """)
    op.execute("""
        INSERT INTO drive_workspaces (id, organization_id, kind, google_drive_id, name, owner_user_id, status, created_at, updated_at)
        SELECT gen_random_uuid(), dc.organization_id, 'my_drive', 'root', 'My Drive', dc.user_id, 'active', now(), now()
        FROM drive_connections dc
    """)
    op.execute("""
        INSERT INTO drive_workspace_connections (id, workspace_id, connection_id, status, updated_at)
        SELECT gen_random_uuid(), dw.id, dc.id, 'active', now()
        FROM drive_workspaces dw JOIN drive_connections dc ON dc.organization_id = dw.organization_id AND dc.user_id = dw.owner_user_id
    """)
    op.execute("""
        INSERT INTO drive_selections (id, workspace_id, user_id, share_all, selected_file_ids, configured, updated_at)
        SELECT gen_random_uuid(), dw.id, ga.user_id, COALESCE(ga.share_all, false), COALESCE(ga.shared_file_ids, '[]'::jsonb), ga.share_all IS NOT NULL, now()
        FROM google_accounts ga JOIN drive_workspaces dw ON dw.owner_user_id = ga.user_id AND dw.kind = 'my_drive'
    """)


def downgrade() -> None:
    op.drop_index("ix_documents_owner_user_id", table_name="documents")
    op.drop_index("ix_documents_drive_workspace_id", table_name="documents")
    op.drop_constraint("fk_documents_owner_user", "documents", type_="foreignkey")
    op.drop_constraint("fk_documents_drive_workspace", "documents", type_="foreignkey")
    op.drop_column("documents", "owner_user_id")
    op.drop_column("documents", "drive_workspace_id")
    op.drop_table("drive_selections")
    op.drop_table("drive_workspace_connections")
    op.drop_index("uq_shared_drive_workspace", table_name="drive_workspaces")
    op.drop_table("drive_workspaces")
    op.drop_table("drive_connections")
    op.drop_table("organization_invitations")
    op.drop_table("organization_memberships")
    op.drop_table("google_identities")
    op.drop_constraint("company_has_google_domain", "organizations", type_="check")
    op.drop_constraint("valid_account_type", "organizations", type_="check")
    op.drop_index("ix_organizations_created_by_user_id", table_name="organizations")
    op.drop_constraint("fk_organizations_created_by", "organizations", type_="foreignkey")
    op.drop_column("organizations", "created_by_user_id")
    op.drop_column("organizations", "google_domain")
    op.drop_column("organizations", "account_type")
