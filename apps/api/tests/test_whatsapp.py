"""WhatsApp connector tests: WAHA is mocked, DB writes roll back."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_engine, get_session
from app.main import app
from app.models import User, WhatsappChat, WhatsappConnection, WhatsappMessage
from app.whatsapp import run_import


class _NoClose:
    """Context manager yielding the shared test session without closing it."""

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


def fake_settings(secret=None):
    return SimpleNamespace(
        waha_webhook_secret=(
            SimpleNamespace(get_secret_value=lambda: secret) if secret else None
        ),
        whatsapp_app_secret=None,
    )


class WhatsappApiTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.user = User(email=f"wa-test-{uuid4()}@example.com")
        self.session.add(self.user)
        self.session.flush()
        self.conn = WhatsappConnection(
            user_id=self.user.id, waha_session=f"u_{self.user.id.hex}", status="WORKING"
        )
        self.session.add(self.conn)
        self.session.flush()

        def override_session():
            yield self.session

        app.dependency_overrides[get_current_user] = lambda: self.user
        app.dependency_overrides[get_session] = override_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def test_connect_creates_session(self):
        self.session.delete(self.conn)
        self.session.flush()
        with (
            patch("app.whatsapp.waha_client.create_session") as create,
            patch("app.whatsapp.waha_client.get_session") as get,
        ):
            get.return_value = {"status": "SCAN_QR_CODE", "me": None}
            resp = self.client.post("/whatsapp/connect")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "SCAN_QR_CODE")
        create.assert_called_once_with(f"u_{self.user.id.hex}")

    def test_connect_status_syncs_remote_state(self):
        with patch("app.whatsapp.waha_client.get_session") as get:
            get.return_value = {
                "status": "WORKING",
                "me": {"id": "6591234567@c.us"},
            }
            resp = self.client.get("/whatsapp/connect/status")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["phone_number"], "6591234567")
        self.assertEqual(self.conn.status, "WORKING")

    def test_chats_requires_connection(self):
        self.session.delete(self.conn)
        self.session.flush()
        resp = self.client.get("/whatsapp/chats")
        self.assertEqual(resp.status_code, 409)

    def test_chats_lists_and_upserts(self):
        with patch("app.whatsapp.waha_client.chats_overview") as overview:
            overview.return_value = [
                {
                    "id": "6591234567@c.us",
                    "name": "Maya",
                    "lastMessage": {"timestamp": 1700000000, "body": "hi"},
                },
                {"id": "120@g.us", "name": "Launch", "lastMessage": None},
            ]
            resp = self.client.get("/whatsapp/chats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 2)
        by_jid = {c["chat_jid"]: c for c in data}
        self.assertEqual(by_jid["6591234567@c.us"]["chat_type"], "contact")
        self.assertEqual(by_jid["120@g.us"]["chat_type"], "group")
        # Second call keeps single rows per chat.
        with patch("app.whatsapp.waha_client.chats_overview", return_value=overview.return_value):
            self.client.get("/whatsapp/chats")
        count = self.session.scalar(
            select(func.count(WhatsappChat.id)).where(
                WhatsappChat.connection_id == self.conn.id
            )
        )
        self.assertEqual(count, 2)

    def test_import_is_idempotent(self):
        chat = WhatsappChat(
            connection_id=self.conn.id, chat_jid="6591234567@c.us", import_status="importing"
        )
        self.session.add(chat)
        self.session.flush()
        page = [
            {
                "id": "false_6591234567@c.us_AAA",
                "timestamp": 1700000000,
                "from": "6591234567@c.us",
                "fromMe": False,
                "body": "hello",
            },
            {
                "id": "true_6591234567@c.us_BBB",
                "timestamp": 1700000060,
                "to": "6591234567@c.us",
                "fromMe": True,
                "body": "hi back",
            },
        ]
        conn_id = self.conn.id
        chat_jid = chat.chat_jid
        with (
            patch("app.whatsapp.Session", new=lambda *a, **k: _NoClose(self.session)),
            patch("app.whatsapp.waha_client.get_messages", return_value=page) as get_msgs,
        ):
            run_import(conn_id, [chat_jid])
            run_import(conn_id, [chat_jid])
        self.session.refresh(chat)
        self.assertEqual(chat.import_status, "imported")
        self.assertEqual(chat.message_count, 2)
        self.assertEqual(get_msgs.call_count, 2)

    def test_webhook_rejects_bad_token(self):
        with patch("app.whatsapp.get_settings", return_value=fake_settings("expected")):
            resp = self.client.post(
                "/whatsapp/webhooks",
                json={"event": "session.status", "session": self.conn.waha_session, "payload": {"status": "FAILED"}},
                headers={"X-Webhook-Token": "wrong"},
            )
        self.assertEqual(resp.status_code, 401)

    def test_webhook_session_status_updates_connection(self):
        with patch("app.whatsapp.get_settings", return_value=fake_settings("tok")):
            resp = self.client.post(
                "/whatsapp/webhooks",
                json={
                    "event": "session.status",
                    "session": self.conn.waha_session,
                    "payload": {"status": "FAILED"},
                },
                headers={"X-Webhook-Token": "tok"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.conn.status, "FAILED")

    def test_webhook_stores_message_on_imported_chat(self):
        chat = WhatsappChat(
            connection_id=self.conn.id,
            chat_jid="6591234567@c.us",
            import_status="imported",
        )
        self.session.add(chat)
        self.session.flush()
        msg = {
            "id": "false_6591234567@c.us_NEW",
            "timestamp": 1700000100,
            "from": "6591234567@c.us",
            "fromMe": False,
            "body": "new inbound",
        }
        with patch("app.whatsapp.get_settings", return_value=fake_settings(None)):
            resp = self.client.post(
                "/whatsapp/webhooks",
                json={
                    "event": "message",
                    "session": self.conn.waha_session,
                    "payload": msg,
                },
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(chat.message_count, 1)
        stored = self.session.scalar(
            select(WhatsappMessage).where(WhatsappMessage.wa_message_id == msg["id"])
        )
        self.assertIsNotNone(stored)
        self.assertEqual(stored.body, "new inbound")

    def test_webhook_ignores_not_imported_chat(self):
        chat = WhatsappChat(
            connection_id=self.conn.id,
            chat_jid="6591234567@c.us",
            import_status="none",
        )
        self.session.add(chat)
        self.session.flush()
        with patch("app.whatsapp.get_settings", return_value=fake_settings(None)):
            resp = self.client.post(
                "/whatsapp/webhooks",
                json={
                    "event": "message",
                    "session": self.conn.waha_session,
                    "payload": {
                        "id": "false_6591234567@c.us_SKIP",
                        "timestamp": 1700000100,
                        "from": "6591234567@c.us",
                        "body": "should not store",
                    },
                },
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(chat.message_count, 0)

    def test_endpoints_require_auth(self):
        app.dependency_overrides.clear()
        client = TestClient(app)
        self.assertEqual(client.post("/whatsapp/connect").status_code, 401)
        self.assertEqual(client.get("/whatsapp/chats").status_code, 401)


if __name__ == "__main__":
    unittest.main()
