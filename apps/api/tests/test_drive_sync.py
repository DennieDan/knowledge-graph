"""Drive sync: metadata mirror, selection filtering, and incremental ingest."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.drive_sync import sync_workspace
from app.models import (
    Document,
    DocumentVersion,
    DriveConnection,
    DriveFile,
    DriveSelection,
    DriveWorkspace,
    GoogleIdentity,
    Organization,
    OrganizationMembership,
    User,
)


def remote_file(file_id, name="file.txt", mime="text/plain", parents=None, modified="2026-01-02T10:00:00Z", md5="abc", trashed=False):
    return {
        "id": file_id,
        "name": name,
        "mimeType": mime,
        "parents": parents or [],
        "modifiedTime": modified,
        "md5Checksum": md5,
        "webViewLink": f"https://drive/{file_id}",
        "trashed": trashed,
    }


class DriveSyncTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")

        self.user = User(email=f"owner-{uuid4()}@acme.example")
        self.session.add(self.user)
        self.session.flush()
        self.session.add(GoogleIdentity(user_id=self.user.id, google_sub=f"sub-{uuid4()}", email=self.user.email))
        self.organization = Organization(name="Sync test", account_type="personal")
        self.session.add(self.organization)
        self.session.flush()
        self.session.add(OrganizationMembership(organization_id=self.organization.id, user_id=self.user.id, role="admin"))
        self.workspace = DriveWorkspace(
            organization_id=self.organization.id,
            kind="my_drive",
            google_drive_id="root",
            name="My Drive",
            owner_user_id=self.user.id,
        )
        self.session.add(self.workspace)
        self.session.flush()
        self.drive_connection = DriveConnection(
            organization_id=self.organization.id,
            user_id=self.user.id,
            google_identity_id=self.session.scalar(select(GoogleIdentity.id).where(GoogleIdentity.user_id == self.user.id)),
            scopes="drive.readonly",
            access_token="token",
            access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        self.session.add(self.drive_connection)
        self.session.flush()
        self.session.add(DriveSelection(workspace_id=self.workspace.id, user_id=self.user.id, share_all=True, configured=True))
        self.session.flush()

        self.lister = patch("app.drive_sync.list_workspace_items")
        self.fetcher = patch("app.drive_sync.fetch_file_text", return_value="file contents")
        self.mock_list = self.lister.start()
        self.mock_fetch = self.fetcher.start()
        self.addCleanup(self.lister.stop)
        self.addCleanup(self.fetcher.stop)

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def set_remote(self, files, folders=None):
        def listing(workspace, connection, session, fields, q=""):
            return folders or [] if "mimeType" in q else files
        self.mock_list.side_effect = listing

    def document_for(self, file_id):
        return self.session.scalar(
            select(Document).where(Document.source == "google_drive", Document.external_id == file_id)
        )

    def test_sync_mirrors_files_and_ingests_supported_types(self):
        self.set_remote([remote_file("f1", "PO2431.txt"), remote_file("f2", "photo", mime="image/png")])
        result = sync_workspace(self.session, self.workspace, self.drive_connection, self.user)
        self.assertEqual({"synced": 2, "ingested": 1, "skipped": 1, "errors": []}, result)
        row = self.session.scalar(select(DriveFile).where(DriveFile.file_id == "f1"))
        self.assertEqual("PO2431.txt", row.name)
        document = self.document_for("f1")
        self.assertEqual(self.workspace.id, document.drive_workspace_id)
        self.assertEqual(self.user.id, document.owner_user_id)

    def own_selection(self):
        return self.session.scalar(
            select(DriveSelection).where(
                DriveSelection.workspace_id == self.workspace.id,
                DriveSelection.user_id == self.user.id,
            )
        )

    def test_unconfigured_selection_ingests_nothing(self):
        selection = self.own_selection()
        selection.configured = False
        self.session.flush()
        self.set_remote([remote_file("f1")])
        result = sync_workspace(self.session, self.workspace, self.drive_connection, self.user)
        self.assertEqual(0, result["ingested"])

    def test_folder_selection_covers_descendants_only(self):
        selection = self.own_selection()
        selection.share_all = False
        selection.selected_file_ids = ["folder-1"]
        self.session.flush()
        self.set_remote(
            [remote_file("in", parents=["folder-1"]), remote_file("out", parents=["folder-2"])],
            folders=[{"id": "folder-1", "parents": []}, {"id": "folder-2", "parents": []}],
        )
        result = sync_workspace(self.session, self.workspace, self.drive_connection, self.user)
        self.assertEqual(1, result["ingested"])
        self.assertIsNotNone(self.document_for("in"))
        self.assertIsNone(self.document_for("out"))

    def test_unchanged_files_are_not_reingested(self):
        self.set_remote([remote_file("f1")])
        sync_workspace(self.session, self.workspace, self.drive_connection, self.user)
        result = sync_workspace(self.session, self.workspace, self.drive_connection, self.user)
        self.assertEqual(0, result["ingested"])
        versions = self.session.scalars(
            select(DocumentVersion).join(Document, Document.id == DocumentVersion.document_id).where(Document.external_id == "f1")
        ).all()
        self.assertEqual(1, len(versions))

    def test_changed_file_produces_a_new_revision(self):
        self.set_remote([remote_file("f1")])
        sync_workspace(self.session, self.workspace, self.drive_connection, self.user)
        self.set_remote([remote_file("f1", modified="2026-01-03T10:00:00Z")])
        self.mock_fetch.return_value = "updated contents"
        result = sync_workspace(self.session, self.workspace, self.drive_connection, self.user)
        self.assertEqual(1, result["ingested"])
        latest = self.session.scalar(
            select(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Document.external_id == "f1")
            .order_by(DocumentVersion.revision.desc())
            .limit(1)
        )
        self.assertEqual(2, latest.revision)

    def test_trashed_and_missing_files_are_marked(self):
        self.set_remote([remote_file("f1"), remote_file("f2", trashed=True)])
        sync_workspace(self.session, self.workspace, self.drive_connection, self.user)
        trashed = self.session.scalar(select(DriveFile).where(DriveFile.file_id == "f2"))
        self.assertTrue(trashed.trashed)
        self.set_remote([])
        sync_workspace(self.session, self.workspace, self.drive_connection, self.user)
        self.assertTrue(self.session.scalar(select(DriveFile).where(DriveFile.file_id == "f1")).trashed)


if __name__ == "__main__":
    unittest.main()
