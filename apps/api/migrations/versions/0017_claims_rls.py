"""Postgres RLS second gate for org isolation (#101 Step 2).

Revision ID: 0017
Revises: 0016

App-layer field filters in record_access remain the primary gate. This
revision enables row-level security as a second wall:

- findings (always present on this branch): SELECT policy keyed to
  app.organization_id GUC.
- claims: same policies only when the table exists (lands with #93 /
  records-claims). Until then the DO block is a no-op for claims.
- substack_contents: SELECT via parent substacks.organization_id, so
  field-like JSON content is gated the same way before claims merge.

Does not FORCE ROW LEVEL SECURITY — the table owner (API role) still
bypasses until request middleware always calls set_request_org and a
follow-up turns FORCE on (or the API connects as a NOBYPASSRLS role).
Tests SET LOCAL ROLE to a non-bypass role inside a rolled-back transaction.
"""
from alembic import op


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# Shared USING expression: unset / empty GUC yields no visible rows.
_ORG_GUC = "organization_id::text = current_setting('app.organization_id', true)"

_SUBSTACK_CONTENTS_ORG = """
EXISTS (
  SELECT 1 FROM substacks s
  WHERE s.id = substack_contents.substack_id
    AND s.organization_id::text = current_setting('app.organization_id', true)
)
"""


def _enable_select_org_rls(table: str, select_using: str) -> None:
    """ENABLE RLS + SELECT org policy + permissive write policies (no FORCE)."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {table}_select_org ON {table}")
    op.execute(
        f"CREATE POLICY {table}_select_org ON {table} FOR SELECT USING ({select_using})"
    )
    for cmd, suffix, body in (
        ("INSERT", "insert", f"WITH CHECK (true)"),
        ("UPDATE", "update", f"USING (true) WITH CHECK (true)"),
        ("DELETE", "delete", f"USING (true)"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_{suffix} ON {table}")
        op.execute(f"CREATE POLICY {table}_{suffix} ON {table} FOR {cmd} {body}")


def _disable_rls(table: str) -> None:
    for suffix in ("select_org", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS {table}_{suffix} ON {table}")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    _enable_select_org_rls("findings", _ORG_GUC)
    _enable_select_org_rls("substack_contents", _SUBSTACK_CONTENTS_ORG)

    # claims table is on the records-claims branch (#93), not field-roles.
    # When that merges, this block attaches the same org SELECT gate.
    op.execute(
        f"""
        DO $$
        BEGIN
          IF to_regclass('public.claims') IS NOT NULL THEN
            ALTER TABLE claims ENABLE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS claims_select_org ON claims;
            CREATE POLICY claims_select_org ON claims
              FOR SELECT USING ({_ORG_GUC});
            DROP POLICY IF EXISTS claims_insert ON claims;
            CREATE POLICY claims_insert ON claims FOR INSERT WITH CHECK (true);
            DROP POLICY IF EXISTS claims_update ON claims;
            CREATE POLICY claims_update ON claims
              FOR UPDATE USING (true) WITH CHECK (true);
            DROP POLICY IF EXISTS claims_delete ON claims;
            CREATE POLICY claims_delete ON claims FOR DELETE USING (true);
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.claims') IS NOT NULL THEN
            DROP POLICY IF EXISTS claims_select_org ON claims;
            DROP POLICY IF EXISTS claims_insert ON claims;
            DROP POLICY IF EXISTS claims_update ON claims;
            DROP POLICY IF EXISTS claims_delete ON claims;
            ALTER TABLE claims DISABLE ROW LEVEL SECURITY;
          END IF;
        END $$;
        """
    )
    _disable_rls("substack_contents")
    _disable_rls("findings")
