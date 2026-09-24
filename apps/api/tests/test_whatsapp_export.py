"""WhatsApp export upload: parser formats, sample fixtures, and the /whatsapp/uploads API."""
import io
import unittest
import zipfile
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_engine, get_session
from app.main import app
from app.models import (
    Document, Organization, OrganizationMembership, Substack, User, WhatsappChat, WhatsappConnection, WhatsappMessage,
)
from app.whatsapp_export import ExportFormatError, parse_export, parse_export_text
from scripts.generate_whatsapp_exports import render_android, render_ios
from scripts.sample_conversations import DATASETS

LRM, NNBSP = "\u200e", "\u202f"

IOS_CHAT = "\n".join([
    f"[14/8/26, 5:39:07{NNBSP}PM] Jon Tan: {LRM}Messages and calls are end-to-end encrypted. Only people in this chat can read, listen to, or share them.",
    f"[14/8/26, 5:42:07{NNBSP}PM] Jon Tan: PO MER-PO-4128 sent",
    f"[14/8/26, 5:45:18{NNBSP}PM] Linh Tran: Received, will ack\nwithin 1 working day",
    f"{LRM}[14/8/26, 5:46:04{NNBSP}PM] Jon Tan: {LRM}image omitted",
    f"{LRM}[17/8/26, 9:03:08{NNBSP}AM] Jon Tan: MER-PO-4128 Rev B.pdf • {LRM}2 pages {LRM}document omitted",
    f"{LRM}[17/8/26, 9:04:00{NNBSP}AM] Jon Tan: {LRM}This message was deleted.",
    f"[17/8/26, 12:10:00{NNBSP}PM] Linh Tran: Qty 60 confirmed {LRM}<This message was edited>",
])

ANDROID_CHAT = "\n".join([
    f"31/08/2026, 8:12{NNBSP}am - Messages and calls are end-to-end encrypted. Only people in this chat can read, listen to, or share them. Learn more.",
    f"31/08/2026, 8:12{NNBSP}am - You created group \"SN Production\"",
    f"31/08/2026, 8:12{NNBSP}am - You added Wei Ming and Priya QC",
    f"31/08/2026, 8:15{NNBSP}am - Linh Tran: Week 36 priorities:",
    "1. SEM-PO-4121 second batch",
    f"31/08/2026, 12:22{NNBSP}pm - Wei Ming: <Media omitted>",
    f"31/08/2026, 12:22{NNBSP}pm - Priya QC: This message was deleted",
]) + "\n"


class ParserTests(unittest.TestCase):
    def test_ios_lines_media_deleted_edited_and_multiline(self):
        chat = parse_export_text(IOS_CHAT, me_name="linh tran")
        self.assertEqual(chat.name, "Jon Tan")
        self.assertEqual(chat.export_format, "ios")
        self.assertEqual(chat.chat_type, "contact")
        self.assertEqual(chat.me_name, "Linh Tran")
        kinds = [m.msg_type for m in chat.messages]
        self.assertEqual(kinds, ["chat", "chat", "image", "document", "revoked", "chat"])
        first = chat.messages[0]
        self.assertEqual(first.sent_at, datetime(2026, 8, 14, 9, 42, 7, tzinfo=timezone.utc))  # 5:42 PM SGT
        self.assertEqual(chat.messages[1].body, "Received, will ack\nwithin 1 working day")
        self.assertTrue(chat.messages[1].from_me)
        self.assertEqual(chat.messages[3].body, "[document] MER-PO-4128 Rev B.pdf")
        self.assertIsNone(chat.messages[4].body)
        self.assertEqual(chat.messages[5].body, "Qty 60 confirmed")
        self.assertTrue(chat.messages[5].edited)
        self.assertEqual(chat.messages[5].sent_at.hour, 4)  # 12:10 PM SGT

    def test_android_group_with_system_lines(self):
        chat = parse_export_text(ANDROID_CHAT, filename="WhatsApp Chat with SN Production.txt", me_name="Linh Tran")
        self.assertEqual(chat.name, "SN Production")
        self.assertEqual(chat.export_format, "android")
        self.assertEqual(chat.chat_type, "group")
        self.assertEqual([m.msg_type for m in chat.messages], ["chat", "media", "revoked"])
        self.assertEqual(chat.messages[0].body, "Week 36 priorities:\n1. SEM-PO-4121 second batch")
        self.assertEqual(chat.messages[1].sent_at.hour, 4)

    def test_us_dates_and_24_hour_clock(self):
        chat = parse_export_text("[9/24/26, 14:05:00] Ana: hi\n[9/25/26, 09:00:00] Ben: yo")
        self.assertEqual(chat.messages[0].sent_at, datetime(2026, 9, 24, 6, 5, tzinfo=timezone.utc))
        self.assertEqual(chat.name, "Ana, Ben")

    def test_ids_are_stable_and_unique_within_same_second(self):
        text = "24/09/2026, 9:14 am - Ana: ok\n24/09/2026, 9:14 am - Ana: ok"
        first = [m.wa_message_id for m in parse_export_text(text).messages]
        again = [m.wa_message_id for m in parse_export_text(text).messages]
        self.assertEqual(first, again)
        self.assertEqual(len(set(first)), 2)

    def test_zip_uses_chat_txt_and_outer_filename(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("_chat.txt", IOS_CHAT)
        chat = parse_export(buffer.getvalue(), "WhatsApp Chat - Jon Tan Meridian.zip")
        self.assertEqual(chat.name, "Jon Tan Meridian")
        self.assertEqual(len(chat.messages), 6)

    def test_rejects_non_exports(self):
        with self.assertRaises(ExportFormatError):
            parse_export(b"hello world", "notes.txt")
        with self.assertRaises(ExportFormatError):
            parse_export(b"PK\x03\x04garbage", "x.zip")

    def test_sample_fixtures_round_trip(self):
        for conversations in DATASETS.values():
            for conversation in conversations:
                render = render_ios if conversation.platform == "ios" else render_android
                chat = parse_export_text(
                    render(conversation),
                    filename=f"WhatsApp Chat with {conversation.name}.txt",
                    me_name=conversation.me,
                )
                self.assertEqual(chat.name, conversation.name)
                self.assertEqual(len(chat.messages), len(conversation.messages), conversation.name)
                self.assertEqual(chat.chat_type, "group" if conversation.group_members else "contact")
                self.assertEqual(chat.export_format, conversation.platform)
                self.assertEqual(
                    sum(m.from_me for m in chat.messages),
                    sum(sender == conversation.me for _, sender, _ in conversation.messages),
                )
                self.assertEqual(chat.messages, sorted(chat.messages, key=lambda m: m.sent_at))


class UploadApiTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.user = User(email=f"wa-upload-{uuid4()}@example.com", display_name="Linh Tran")
        self.session.add(self.user)
        self.session.flush()
        self.organization = Organization(name="Upload test", account_type="personal")
        self.session.add(self.organization)
        self.session.flush()
        self.session.add(OrganizationMembership(organization_id=self.organization.id, user_id=self.user.id, role="admin"))
        self.session.flush()

        def override_session():
            yield self.session

        app.dependency_overrides[get_current_user] = lambda: self.user
        app.dependency_overrides[get_session] = override_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def upload(self, text=ANDROID_CHAT, name="WhatsApp Chat with SN Production.txt", organization_id=None):
        return self.client.post(
            "/whatsapp/uploads",
            files={"file": (name, text.encode(), "text/plain")},
            data={"organization_id": str(organization_id or self.organization.id)},
        )

    def test_upload_stores_chat_ingests_and_stays_unlinked(self):
        resp = self.upload()
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["name"], "SN Production")
        self.assertEqual(body["message_count"], 3)
        self.assertEqual(body["me_name"], "Linh Tran")
        self.assertEqual(body["import_status"], "imported")
        conn = self.session.scalar(select(WhatsappConnection).where(WhatsappConnection.user_id == self.user.id))
        self.assertEqual(conn.status, "STOPPED")
        chat = self.session.scalar(select(WhatsappChat).where(WhatsappChat.chat_jid == body["chat_jid"]))
        self.assertEqual(chat.origin, "export")
        document = self.session.scalar(select(Document).where(Document.external_id == chat.chat_jid))
        self.assertIsNotNone(document)
        self.assertEqual(document.owner_user_id, self.user.id)

        uploads = self.client.get("/whatsapp/uploads").json()
        self.assertEqual([u["chat_jid"] for u in uploads], [body["chat_jid"]])
        self.assertEqual(self.client.get("/whatsapp/imports").json(), [])

    def test_reupload_is_idempotent_and_appends(self):
        first = self.upload().json()
        again = self.upload().json()
        self.assertEqual(again["chat_jid"], first["chat_jid"])
        self.assertEqual(again["new_messages"], 0)
        longer = ANDROID_CHAT + f"01/09/2026, 9:00{NNBSP}am - Wei Ming: Spindle fixed\n"
        third = self.upload(longer).json()
        self.assertEqual(third["new_messages"], 1)
        self.assertEqual(third["message_count"], 4)

    def test_upload_requires_membership_and_valid_export(self):
        self.assertEqual(self.upload(organization_id=uuid4()).status_code, 404)
        resp = self.upload(text="just some notes", name="notes.txt")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["detail"], "not_a_whatsapp_export")

    def test_wipe_removes_chats_documents_and_conversation_records(self):
        body = self.upload().json()
        document = self.session.scalar(select(Document).where(Document.external_id == body["chat_jid"]))
        self.assertIsNotNone(document)
        resp = self.client.delete("/whatsapp/uploads")
        self.assertEqual(resp.json(), {"deleted": 1})
        self.assertIsNone(self.session.scalar(select(Document).where(Document.external_id == body["chat_jid"])))
        self.assertEqual(self.session.scalar(select(func.count(WhatsappMessage.id)).join(WhatsappChat).where(WhatsappChat.chat_jid == body["chat_jid"])), 0)
        self.assertIsNone(self.session.scalar(select(WhatsappConnection).where(WhatsappConnection.user_id == self.user.id)))
        self.assertEqual(
            self.session.scalar(select(func.count(Substack.id)).where(
                Substack.organization_id == self.organization.id, Substack.stack_type == "conversations",
            )),
            0,
        )

    def test_disconnect_keeps_uploaded_chats(self):
        body = self.upload().json()
        conn = self.session.scalar(select(WhatsappConnection).where(WhatsappConnection.user_id == self.user.id))
        conn.status = "WORKING"
        self.session.add(WhatsappChat(connection_id=conn.id, chat_jid="6591234567@c.us", origin="waha"))
        self.session.flush()
        with patch("app.whatsapp.waha_client.delete_session"):
            self.assertEqual(self.client.delete("/whatsapp/connect").status_code, 200)
        jids = set(self.session.scalars(select(WhatsappChat.chat_jid).where(WhatsappChat.connection_id == conn.id)))
        self.assertEqual(jids, {body["chat_jid"]})
        self.assertEqual(conn.status, "STOPPED")


if __name__ == "__main__":
    unittest.main()
