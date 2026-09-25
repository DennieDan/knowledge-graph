"""The assistant connector (#94 F-03): keys, walls, read-only, and the MCP wire.

Invented data only. Every test runs inside one transaction that is rolled back;
the connector's own sessions are pointed at it through `open_session`.
"""
import json
import logging
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import anyio
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import connector
from app.auth import get_current_user
from app.claims import create_claim
from app.connector import (
    RecordNotFound,
    find_records,
    open_record,
    read_only,
    record_history,
)
from app.connector_keys import ConnectorScope, create_key, resolve_key
from app.database import get_engine, get_session
from app.ingest import SourceDocument, ingest_document
from app.main import app
from app.models import (
    Chunk,
    ConfirmEvent,
    ConnectorKey,
    ContentCitation,
    OrderEvent,
    Organization,
    OrganizationMembership,
    Record,
    Substack,
    SubstackContent,
    SubstackSource,
    User,
)

MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")

        self.alice = User(email=f"alice-{uuid4()}@acme.example", display_name="Alice Tan")
        self.bob = User(email=f"bob-{uuid4()}@acme.example", display_name="Bob Lim")
        self.pat = User(email=f"pat-{uuid4()}@acme.example", display_name="Pat Ong")
        self.session.add_all([self.alice, self.bob, self.pat])
        self.session.flush()
        self.organization = Organization(name="Kestrel Precision", account_type="personal")
        self.other = Organization(name="Other company", account_type="personal")
        self.session.add_all([self.organization, self.other])
        self.session.flush()
        self.session.add_all([
            OrganizationMembership(organization_id=self.organization.id, user_id=self.alice.id, role="admin"),
            OrganizationMembership(organization_id=self.organization.id, user_id=self.bob.id, role="member"),
            OrganizationMembership(organization_id=self.organization.id, user_id=self.pat.id, role="planner"),
            OrganizationMembership(organization_id=self.other.id, user_id=self.bob.id, role="admin"),
        ])
        self.session.flush()
        self.scope = ConnectorScope(key_id=uuid4(), organization_id=self.organization.id, user_id=self.alice.id, role="admin")

        self.current_user = self.alice

        def override_session():
            yield self.session

        app.dependency_overrides[get_current_user] = lambda: self.current_user
        app.dependency_overrides[get_session] = override_session
        self.sessions = patch.object(connector, "open_session", self.connector_session)
        self.sessions.start()

    def tearDown(self):
        self.sessions.stop()
        connector._process_scope = None
        app.dependency_overrides.clear()
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def connector_session(self):
        return Session(self.connection, join_transaction_mode="create_savepoint")

    # ----- invented data

    def document(self, title, content, owner=None, organization=None, source="google_drive"):
        version = ingest_document(
            self.session,
            (organization or self.organization).id,
            SourceDocument(
                source=source,
                external_id=f"ext-{uuid4()}",
                title=title,
                content=content,
                owner_user_id=owner,
                source_uri=f"https://drive.example/{uuid4()}" if source == "google_drive" else None,
            ),
        )
        self.session.flush()
        return version

    def chunk(self, version):
        return self.session.scalars(
            select(Chunk).where(Chunk.document_version_id == version.id).order_by(Chunk.position)
        ).first()

    def record(self, name, *, segments, citations=(), organization=None, owner=None, status="confirmed",
               confirmed_by=None, stack_type="sales-orders", identity_key=None, revision=1):
        substack = Substack(
            organization_id=(organization or self.organization).id,
            stack_type=stack_type,
            name=name,
            identity_key=identity_key,
            identity_kind="name" if identity_key else None,
            owner_user_id=owner,
            status="confirmed" if status == "confirmed" else "proposed",
        )
        self.session.add(substack)
        self.session.flush()
        content = self.content(substack, segments=segments, citations=citations, status=status,
                               confirmed_by=confirmed_by, revision=revision)
        return substack, content

    def content(self, substack, *, segments, citations=(), status="confirmed", confirmed_by=None, revision=1):
        content = SubstackContent(
            substack_id=substack.id,
            revision=revision,
            prompt_key="orders.read.v0",
            prompt_version="v0",
            model="fake-reader",
            content={"segments": segments, "entries": []},
            status=status,
            inputs_fingerprint="a" * 64,
            confirmed_by_user_id=confirmed_by.id if confirmed_by else None,
            confirmed_at=datetime(2026, 9, 24, 9, 30, tzinfo=timezone.utc) if status == "confirmed" else None,
        )
        self.session.add(content)
        self.session.flush()
        filed = set(self.session.scalars(select(SubstackSource.document_id).where(SubstackSource.substack_id == substack.id)))
        for segment_index, version in citations:
            self.session.add(ContentCitation(
                content_id=content.id,
                segment_index=segment_index,
                chunk_id=self.chunk(version).id,
                document_id=version.document_id,
            ))
            if version.document_id not in filed:
                self.session.add(SubstackSource(substack_id=substack.id, document_id=version.document_id, role="evidence"))
                filed.add(version.document_id)
            self.session.flush()
        return content

    def key(self, user, organization=None, name="Claude"):
        row, key = create_key(self.session, organization_id=(organization or self.organization).id, user_id=user.id, name=name)
        self.session.flush()
        return row, key

    # ----- keys

    def test_a_key_reads_as_its_holder_until_switched_off(self):
        row, key = self.key(self.alice)

        scope = resolve_key(self.session, key)

        self.assertEqual((self.organization.id, self.alice.id, "admin"), (scope.organization_id, scope.user_id, scope.role))
        self.assertIsNone(resolve_key(self.session, key + "x"))
        self.assertIsNone(resolve_key(self.session, "not-a-key"))
        self.assertEqual(64, len(row.token_hash))
        self.assertNotIn(key, (row.token_hash, row.prefix))
        row.revoked_at = datetime.now(timezone.utc)
        self.session.flush()
        self.assertIsNone(resolve_key(self.session, key))

    def test_removal_or_a_price_hidden_role_cuts_the_key_off(self):
        _, key = self.key(self.bob)
        membership = self.session.scalar(select(OrganizationMembership).where(
            OrganizationMembership.organization_id == self.organization.id,
            OrganizationMembership.user_id == self.bob.id,
        ))
        membership.role = "supervisor"
        self.session.flush()
        self.assertIsNone(resolve_key(self.session, key))
        self.session.delete(membership)
        self.session.flush()
        self.assertIsNone(resolve_key(self.session, key))

    def test_settings_list_create_and_switch_off(self):
        client = TestClient(app)
        created = client.post(f"/accounts/{self.organization.id}/connector-keys", json={"name": "Claude Desktop"})
        self.assertEqual(201, created.status_code)
        body = created.json()
        self.assertTrue(body["key"].startswith("ck_"))
        self.assertTrue(body["url"].endswith("/mcp"))
        self.assertEqual(f"{body['url']}/k/{body['key']}", body["url_with_key"])

        self.current_user = self.bob
        bobs = client.post(f"/accounts/{self.organization.id}/connector-keys", json={"name": "ChatGPT"}).json()
        listed = client.get(f"/accounts/{self.organization.id}/connector-keys").json()
        self.assertEqual(["ChatGPT"], [item["name"] for item in listed["keys"]])  # members see their own
        self.assertNotIn("key", listed["keys"][0])
        self.assertEqual(404, client.delete(f"/accounts/{self.organization.id}/connector-keys/{body['id']}").status_code)

        self.current_user = self.alice
        listed = client.get(f"/accounts/{self.organization.id}/connector-keys").json()
        self.assertEqual({"Claude Desktop", "ChatGPT"}, {item["name"] for item in listed["keys"]})  # the admin sees all
        switched = client.delete(f"/accounts/{self.organization.id}/connector-keys/{bobs['id']}")
        self.assertEqual(200, switched.status_code)
        self.assertIsNotNone(switched.json()["revoked_at"])
        self.assertIsNone(resolve_key(self.session, bobs["key"]))

    def test_no_keys_for_roles_whose_field_rules_cannot_reach_prose_yet(self):
        self.current_user = self.pat
        client = TestClient(app)
        refused = client.post(f"/accounts/{self.organization.id}/connector-keys", json={"name": "Claude"})
        self.assertEqual(403, refused.status_code)
        self.assertEqual("connector_not_available_for_role", refused.json()["detail"])
        self.assertFalse(client.get(f"/accounts/{self.organization.id}/connector-keys").json()["can_connect"])

    # ----- search

    def test_search_finds_confirmed_records_first_in_chatgpts_shape(self):
        self.record("PO2431 rev A", identity_key="PO2431-A", status="proposed", segments=[])
        confirmed, _ = self.record("PO2431 rev B", identity_key="PO2431-B", confirmed_by=self.bob, segments=[])

        found = find_records(self.session, self.scope, "  PO2431   quantity ")

        self.assertEqual(str(confirmed.id), found.results[0].id)
        self.assertEqual("PO2431 rev B · Sales order · Confirmed by Bob Lim on 2026-09-24", found.results[0].title)
        self.assertIn("Not confirmed by anyone yet", found.results[1].title)
        self.assertTrue(found.results[0].url.endswith(f"/stacks/sales-orders/{confirmed.id}"))
        self.assertEqual({"id", "title", "url"}, set(found.results[0].model_dump()))
        self.assertEqual([], find_records(self.session, self.scope, "   ").results)

    def test_search_keeps_to_the_holders_walls(self):
        self.record("PO7001 shared", identity_key="PO7001-S", segments=[])
        mine, _ = self.record("PO7001 alice only", identity_key="PO7001-A", owner=self.alice.id, segments=[])
        self.record("PO7001 bob only", identity_key="PO7001-B", owner=self.bob.id, segments=[])
        self.record("PO7001 other company", identity_key="PO7001-O", organization=self.other, segments=[])

        names = {result.title.split(" · ")[0] for result in find_records(self.session, self.scope, "PO7001").results}

        self.assertEqual({"PO7001 shared", "PO7001 alice only"}, names)
        self.assertIn(str(mine.id), {result.id for result in find_records(self.session, self.scope, "PO7001").results})

    # ----- fetch

    def test_fetch_marks_each_line_with_its_source_and_quotes_the_passage(self):
        po = self.document("PO HH-2231.pdf", "Harbour Hotel PO HH-2231: 40 cases of basil, deliver 3 Oct.")
        record, content = self.record(
            "PO HH-2231",
            confirmed_by=self.bob,
            segments=[
                {"kind": "field", "name": "quantity", "value": "40 cases"},
                {"kind": "text", "value": "Deliver on 3 Oct to the hotel's loading bay."},
            ],
            citations=[(0, po), (1, po)],
        )
        self.content(record, segments=[{"kind": "field", "name": "quantity", "value": "60 cases"}],
                     status="proposed", revision=2)

        fetched = open_record(self.session, self.scope, str(record.id))

        self.assertIn("Sales order: PO HH-2231", fetched.text)
        self.assertIn("Status: Confirmed by Bob Lim on 2026-09-24", fetched.text)
        self.assertIn("- quantity: 40 cases [S1]", fetched.text)
        self.assertNotIn("60 cases", fetched.text)
        self.assertIn("revision 2) is waiting for review", fetched.text)
        self.assertIn("[S1] PO HH-2231.pdf · Google Drive · https://drive.example/", fetched.text)
        self.assertIn('"Harbour Hotel PO HH-2231: 40 cases of basil, deliver 3 Oct."', fetched.text)
        self.assertEqual("person", fetched.metadata.checked)
        self.assertEqual(2, fetched.metadata.pending_revision)
        self.assertEqual(["S1"], [source.ref for source in fetched.metadata.sources])

    def test_fetch_withholds_lines_read_only_from_someone_elses_private_chat(self):
        shared = self.document("Order sheet.pdf", "Kestrel order 88 brackets.")
        private = self.document("Bob and buyer", "Buyer: keep the discount between us.", owner=self.bob.id, source="whatsapp")
        record, _ = self.record(
            "PO5510",
            confirmed_by=self.alice,
            segments=[
                {"kind": "text", "value": "88 brackets."},
                {"kind": "text", "value": "Discount agreed privately."},
            ],
            citations=[(0, shared), (1, private)],
        )

        seen_by_alice = open_record(self.session, self.scope, str(record.id))
        bob = ConnectorScope(key_id=uuid4(), organization_id=self.organization.id, user_id=self.bob.id, role="member")
        seen_by_bob = open_record(self.session, bob, str(record.id))

        self.assertNotIn("Discount", seen_by_alice.text)
        self.assertNotIn("keep the discount", seen_by_alice.text)
        self.assertEqual(1, seen_by_alice.metadata.withheld_lines)
        self.assertIn("1 line(s) withheld", seen_by_alice.text)
        self.assertIn("Discount agreed privately. [S2]", seen_by_bob.text)

    def test_fetch_applies_the_holders_field_rules(self):
        record, _ = self.record(
            "PO6620",
            confirmed_by=self.alice,
            segments=[
                {"kind": "field", "name": "quantity", "value": "12"},
                {"kind": "field", "name": "unit_price", "value": "S$4.20"},
            ],
        )
        planner = ConnectorScope(key_id=uuid4(), organization_id=self.organization.id, user_id=self.pat.id, role="planner")

        self.assertIn("unit_price: S$4.20", open_record(self.session, self.scope, str(record.id)).text)
        as_planner = open_record(self.session, planner, str(record.id))
        self.assertNotIn("4.20", as_planner.text)
        self.assertIn("quantity: 12", as_planner.text)
        self.assertEqual(1, as_planner.metadata.withheld_lines)

    def test_fetch_shows_facts_confirmed_one_by_one_within_their_walls(self):
        record, _ = self.record("PO7300", confirmed_by=self.alice, segments=[])
        bridged = Record(organization_id=self.organization.id, stack_key="sales-orders", substack_id=record.id)
        self.session.add(bridged)
        self.session.flush()
        create_claim(self.session, organization_id=self.organization.id, record_id=bridged.id, field_key="quantity",
                     value_type="numeric", value_numeric=Decimal("300"), origin="google_drive", quote="Qty: 300 pcs",
                     status="confirmed", confirmed_by_user_id=self.bob.id,
                     confirmed_at=datetime(2026, 9, 23, tzinfo=timezone.utc))
        create_claim(self.session, organization_id=self.organization.id, record_id=bridged.id, field_key="due_date",
                     value_type="text", value_text="10 Oct", origin="whatsapp", quote="can we do 10 Oct",
                     visible_via_user_id=self.bob.id)
        create_claim(self.session, organization_id=self.organization.id, record_id=bridged.id, field_key="unit_price",
                     value_type="numeric", value_numeric=Decimal("1.10"), origin="google_drive", quote="S$1.10 each")

        text = open_record(self.session, self.scope, str(record.id)).text
        planner = ConnectorScope(key_id=uuid4(), organization_id=self.organization.id, user_id=self.pat.id, role="planner")
        planner_text = open_record(self.session, planner, str(record.id)).text

        self.assertIn('- quantity: 300 (confirmed by Bob Lim on 2026-09-23) — quote: "Qty: 300 pcs"', text)
        self.assertIn("- unit_price: 1.10 (proposed, not confirmed)", text)
        self.assertNotIn("10 Oct", text)  # read from Bob's chat
        self.assertNotIn("1.10", planner_text)

    def test_fetch_and_history_refuse_records_outside_the_walls(self):
        theirs, _ = self.record("PO8800", organization=self.other, segments=[])
        private, _ = self.record("PO8801", owner=self.bob.id, segments=[])
        for record_id in (str(theirs.id), str(private.id), "not-a-uuid", str(uuid4())):
            with self.assertRaises(RecordNotFound):
                open_record(self.session, self.scope, record_id)
            with self.assertRaises(RecordNotFound):
                record_history(self.session, self.scope, record_id)

    # ----- history

    def test_history_lists_revisions_confirms_and_order_events_oldest_first(self):
        record, content = self.record("PO9100", status="proposed", segments=[])
        content.created_at = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
        bridged = Record(organization_id=self.organization.id, stack_key="sales-orders", substack_id=record.id)
        self.session.add(bridged)
        self.session.flush()
        self.session.add_all([
            ConfirmEvent(organization_id=self.organization.id, substack_id=record.id, content_id=content.id,
                         kind="auto", at=datetime(2026, 9, 20, 8, 1, tzinfo=timezone.utc)),
            ConfirmEvent(organization_id=self.organization.id, substack_id=record.id, content_id=content.id,
                         kind="person", by_user_id=self.bob.id, at=datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)),
            OrderEvent(organization_id=self.organization.id, order_id=bridged.id, kind="edited", actor_user_id=self.alice.id,
                       at=datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc), payload={"after": {"unit_price": "9.99"}}),
        ])
        self.session.flush()

        events = record_history(self.session, self.scope, str(record.id)).events

        self.assertEqual(["revision", "auto", "person", "edited"], [event.kind for event in events])
        self.assertEqual("Confirmed by Bob Lim, one record (revision 1)", events[2].detail)
        self.assertEqual("Edited by Alice Tan", events[3].detail)
        self.assertNotIn("9.99", json.dumps([event.model_dump() for event in events]))

    # ----- read-only

    def test_connector_sessions_cannot_write(self):
        with read_only(self.scope) as session:
            with self.assertRaises(DBAPIError) as raised:
                session.add(User(email=f"sneaky-{uuid4()}@acme.example"))
                session.flush()
        self.assertIn("read-only", str(raised.exception).lower())
        self.session.add(User(email=f"after-{uuid4()}@acme.example"))
        self.session.flush()  # the test transaction itself is still writable

    # ----- the wire

    def test_mcp_tools_are_read_only_and_answer_in_structured_json(self):
        record, _ = self.record("PO4400", identity_key="PO4400", confirmed_by=self.bob,
                                segments=[{"kind": "field", "name": "quantity", "value": "7"}])
        connector._process_scope = self.scope

        async def call():
            async with create_connected_server_and_client_session(connector.server._mcp_server) as client:
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                found = await client.call_tool("search", {"query": "PO4400"})
                opened = await client.call_tool("fetch", {"id": str(record.id)})
                missing = await client.call_tool("history", {"id": str(uuid4())})
                return tools, found, opened, missing

        tools, found, opened, missing = anyio.run(call)

        self.assertEqual({"search", "fetch", "history"}, set(tools))
        for tool in tools.values():
            self.assertTrue(tool.annotations.readOnlyHint)
            self.assertFalse(tool.annotations.destructiveHint)
            self.assertIsNotNone(tool.outputSchema)
        self.assertEqual(str(record.id), found.structuredContent["results"][0]["id"])
        self.assertEqual(found.structuredContent, json.loads(found.content[0].text))  # ChatGPT reads the text copy
        self.assertIn("- quantity: 7", opened.structuredContent["text"])
        self.assertTrue(missing.isError)
        self.assertIn("record_not_found", missing.content[0].text)

    def test_http_needs_a_live_key_in_the_header_or_the_url(self):
        record, _ = self.record("PO4500", identity_key="PO4500", confirmed_by=self.bob, segments=[])
        row, key = self.key(self.alice)
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "search", "arguments": {"query": "PO4500"}}}

        with TestClient(app) as client:
            by_header = client.post("/mcp", json=call, headers={**MCP_HEADERS, "Authorization": f"Bearer {key}"})
            by_url = client.post(f"/mcp/k/{key}", json=call, headers=MCP_HEADERS)
            no_key = client.post("/mcp", json=call, headers=MCP_HEADERS)
            wrong = client.post("/mcp/k/ck_wrong", json=call, headers=MCP_HEADERS)
            row.revoked_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            self.session.flush()
            revoked = client.post("/mcp", json=call, headers={**MCP_HEADERS, "Authorization": f"Bearer {key}"})

        for response in (by_header, by_url):
            self.assertEqual(200, response.status_code, response.text)
            result = response.json()["result"]
            self.assertFalse(result["isError"])
            self.assertEqual(str(record.id), result["structuredContent"]["results"][0]["id"])
        self.assertEqual([401, 401, 401], [no_key.status_code, wrong.status_code, revoked.status_code])
        self.session.refresh(row)
        self.assertIsNotNone(row.last_used_at)

    def test_keys_in_urls_stay_out_of_the_access_log(self):
        record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                                   ("1.2.3.4:5", "POST", "/mcp/k/ck_secretvalue", "1.1", 200), None)
        connector._RedactKeys().filter(record)
        self.assertNotIn("ck_secretvalue", record.getMessage())
        self.assertIn("/mcp/k/***", record.getMessage())


if __name__ == "__main__":
    unittest.main()
