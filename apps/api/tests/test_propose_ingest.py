"""#92 Steps 2–5: HMAC webhook, PDF text extract, propose quote gate."""
import hashlib
import hmac
import io
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_engine, get_session
from app.ingest import extract_pdf_text
from app.main import app
from app.models import User, WhatsappConnection, WhatsappMessage
from app.propose import propose_from_message, propose_from_text, quotable_fields
from app.whatsapp import hmac_sha256_hex, verify_hub_signature


def fake_settings(*, waha_secret=None, app_secret=None):
    return SimpleNamespace(
        waha_webhook_secret=(
            SimpleNamespace(get_secret_value=lambda: waha_secret) if waha_secret else None
        ),
        whatsapp_app_secret=(
            SimpleNamespace(get_secret_value=lambda: app_secret) if app_secret else None
        ),
    )


def make_pdf(lines: list[str]) -> bytes:
    """Minimal text-layer PDF (same pattern as scripts.seed_drive.make_pdf)."""
    per_page = 45
    pages = [lines[i : i + per_page] for i in range(0, len(lines), per_page)] or [[]]

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    kids = " ".join(f"{4 + i * 2} 0 R" for i in range(len(pages)))
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, page_lines in enumerate(pages):
        content_obj = 5 + i * 2
        stream = ["BT /F1 10 Tf 50 780 Td 14 TL"]
        for j, line in enumerate(page_lines):
            if j:
                stream.append("T*")
            stream.append(f"({esc(line)}) Tj")
        stream.append("ET")
        data = "\n".join(stream).encode("latin-1", "replace")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>"
        )
        objects.append(f"<< /Length {len(data)} >>\nstream\n" + data.decode() + "\nendstream")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1"))
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF".encode()
    )
    return out.getvalue()


class HubSignatureTests(unittest.TestCase):
    def test_verify_accepts_matching_hmac(self):
        raw = b'{"object":"whatsapp_business_account"}'
        secret = "test-app-secret"
        sig = "sha256=" + hmac_sha256_hex(secret, raw)
        self.assertTrue(verify_hub_signature(raw, sig, secret))

    def test_verify_rejects_bad_hmac(self):
        raw = b'{"object":"whatsapp_business_account"}'
        self.assertFalse(verify_hub_signature(raw, "sha256=" + "0" * 64, "test-app-secret"))


class WhatsappHmacWebhookTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.user = User(email=f"hmac-{uuid4()}@example.com")
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

    def test_hub_signature_accept(self):
        body = b'{"object":"whatsapp_business_account","entry":[]}'
        secret = "meta-secret"
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with patch("app.whatsapp.get_settings", return_value=fake_settings(app_secret=secret)):
            resp = self.client.post(
                "/whatsapp/webhooks",
                content=body,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_hub_signature_reject(self):
        body = b'{"object":"whatsapp_business_account","entry":[]}'
        with patch("app.whatsapp.get_settings", return_value=fake_settings(app_secret="meta-secret")):
            resp = self.client.post(
                "/whatsapp/webhooks",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": "sha256=" + "ab" * 32,
                },
            )
        self.assertEqual(resp.status_code, 403)

    def test_waha_path_still_works_without_hub_header(self):
        with patch("app.whatsapp.get_settings", return_value=fake_settings(waha_secret=None)):
            resp = self.client.post(
                "/whatsapp/webhooks",
                json={
                    "event": "session.status",
                    "session": self.conn.waha_session,
                    "payload": {"status": "FAILED"},
                },
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.conn.status, "FAILED")


class PdfExtractTests(unittest.TestCase):
    def test_extract_pdf_text_from_minimal_bytes(self):
        data = make_pdf(["Purchase Order PO-2431", "Buyer: Acme Hotels"])
        text = extract_pdf_text(data)
        self.assertIn("PO-2431", text)
        self.assertIn("Acme Hotels", text)


class ProposeQuoteTests(unittest.TestCase):
    def test_drops_invented_quotes(self):
        text = "Purchase Order PO-1001 for 12 pcs stainless brackets."
        kept = quotable_fields(
            text,
            [
                {"name": "order_number", "value": "PO-1001", "quote": "PO-1001"},
                {"name": "ghost", "value": "invented", "quote": "this quote is not in the source"},
            ],
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].name, "order_number")
        self.assertEqual(kept[0].value, "PO-1001")

    def test_propose_from_text_without_openai_uses_rules(self):
        text = "Purchase Order PO-2431\nBuyer: Acme Hotels\nQty: 12 pcs"
        with patch("app.propose.get_settings", return_value=SimpleNamespace(openai_api_key=None)):
            proposal = propose_from_text(text, source="google_drive")
        self.assertEqual(proposal.stack, "sales-orders")
        self.assertEqual(proposal.read_by[0], "rules")
        names = {f.name for f in proposal.fields}
        self.assertIn("order_number", names)
        for item in proposal.fields:
            self.assertIn(item.quote, text)

    def test_propose_from_message_uses_stored_row(self):
        msg = WhatsappMessage(
            wa_message_id="m1",
            sent_at=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            sender_name="Ali",
            body="Please confirm PO-9001 for tomorrow",
            from_me=False,
        )
        with patch("app.propose.get_settings", return_value=SimpleNamespace(openai_api_key=None)):
            proposal = propose_from_message(msg)
        self.assertEqual(proposal.stack, "conversations")
        self.assertEqual(proposal.evidence["wa_message_id"], "m1")
        self.assertEqual(proposal.evidence["sender"], "Ali")


class DrivePdfFetchTests(unittest.TestCase):
    def test_pdf_mime_is_no_longer_unsupported(self):
        import httpx
        from app.drive import fetch_file_text

        pdf = make_pdf(["Hello from PDF"])
        with patch("app.drive.httpx.get", return_value=httpx.Response(200, content=pdf)):
            text = fetch_file_text("token", {"id": "f1", "mimeType": "application/pdf"})
        self.assertIn("Hello from PDF", text)


if __name__ == "__main__":
    unittest.main()
