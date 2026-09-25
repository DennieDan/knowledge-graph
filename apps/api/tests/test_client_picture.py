"""Degree-capped client picture walk (#99 Step 1).

Invented data only. Tests focus on the cap seam: depth, per-node degree,
node budget, visited cycles, and destination readability.
"""
from uuid import uuid4
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_engine, get_session
from app.graph import walk_neighbourhood, NeighbourEdge, DEFAULT_MAX_NEIGHBOURS
from app.main import app
from app.models import (
    Organization,
    OrganizationMembership,
    Record,
    RecordLink,
    Substack,
    SubstackLink,
    User,
)


def _edge(neighbour_id, relation="related", source="substack_link"):
    return NeighbourEdge(
        neighbour_id=neighbour_id,
        relation=relation,
        source=source,
        direction="out",
    )


class WalkNeighbourhoodUnitTests(unittest.TestCase):
    def test_max_depth_stops_at_two_hops(self):
        a, b, c, d = uuid4(), uuid4(), uuid4(), uuid4()
        adjacency = {
            a: [_edge(b)],
            b: [_edge(c)],
            c: [_edge(d)],
        }
        walk = walk_neighbourhood(
            a, adjacency, readable={a, b, c, d}, max_depth=2, max_nodes=50, max_neighbours_per_node=8
        )
        self.assertEqual(set(walk.node_ids), {a, b, c})
        self.assertEqual(walk.depths[c], 2)
        self.assertNotIn(d, walk.depths)

    def test_degree_cap_omits_extra_neighbours(self):
        hub = uuid4()
        spokes = [uuid4() for _ in range(12)]
        adjacency = {hub: [_edge(s) for s in spokes]}
        for s in spokes:
            adjacency[s] = []
        walk = walk_neighbourhood(
            hub,
            adjacency,
            readable={hub, *spokes},
            max_depth=2,
            max_nodes=50,
            max_neighbours_per_node=8,
        )
        self.assertEqual(len(walk.node_ids), 1 + 8)
        self.assertEqual(walk.omitted_neighbours[hub], 4)
        kept = set(walk.node_ids) - {hub}
        self.assertEqual(len(kept), 8)
        self.assertTrue(kept.issubset(set(spokes)))

    def test_node_budget_truncates(self):
        root = uuid4()
        children = [uuid4() for _ in range(10)]
        adjacency = {root: [_edge(c) for c in children]}
        for c in children:
            adjacency[c] = []
        walk = walk_neighbourhood(
            root,
            adjacency,
            readable={root, *children},
            max_depth=2,
            max_nodes=5,
            max_neighbours_per_node=20,
        )
        self.assertEqual(len(walk.node_ids), 5)
        self.assertTrue(walk.truncated)

    def test_visited_set_handles_cycles(self):
        a, b = uuid4(), uuid4()
        adjacency = {
            a: [_edge(b)],
            b: [_edge(a)],
        }
        walk = walk_neighbourhood(
            a, adjacency, readable={a, b}, max_depth=2, max_nodes=50, max_neighbours_per_node=8
        )
        self.assertEqual(set(walk.node_ids), {a, b})
        self.assertEqual(len(walk.edges), 1)

    def test_unreadable_destination_is_hidden(self):
        a, secret, public = uuid4(), uuid4(), uuid4()
        adjacency = {a: [_edge(secret), _edge(public)]}
        walk = walk_neighbourhood(
            a,
            adjacency,
            readable={a, public},
            max_depth=2,
            max_nodes=50,
            max_neighbours_per_node=8,
        )
        self.assertEqual(set(walk.node_ids), {a, public})
        self.assertTrue(all(edge[1] != secret for edge in walk.edges))


class ClientPictureApiTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")

        self.alice = User(email=f"alice-{uuid4()}@acme.example")
        self.bob = User(email=f"bob-{uuid4()}@acme.example")
        self.session.add_all([self.alice, self.bob])
        self.session.flush()
        self.organization = Organization(name="Picture test", account_type="personal")
        self.session.add(self.organization)
        self.session.flush()
        self.session.add_all([
            OrganizationMembership(organization_id=self.organization.id, user_id=self.alice.id, role="admin"),
            OrganizationMembership(organization_id=self.organization.id, user_id=self.bob.id, role="member"),
        ])
        self.session.flush()
        self.current_user = self.alice

        def override_session():
            yield self.session

        app.dependency_overrides[get_current_user] = lambda: self.current_user
        app.dependency_overrides[get_session] = override_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def _substack(self, stack_type: str, name: str, owner=None) -> Substack:
        row = Substack(
            organization_id=self.organization.id,
            stack_type=stack_type,
            name=name,
            status="confirmed",
            created_by="user",
            created_by_user_id=self.alice.id,
            owner_user_id=owner,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def test_picture_uses_substack_and_record_links_with_degree_cap(self):
        client = self._substack("clients", "Kestrel Fabrication")
        orders = [self._substack("sales-orders", f"PO-{i:04d}") for i in range(10)]
        item = self._substack("items", "Bracket A")

        for order in orders:
            self.session.add(
                SubstackLink(
                    substack_id=client.id,
                    related_substack_id=order.id,
                    reason="customer_of",
                )
            )

        # Second hop via record_links: first order → item.
        order_record = Record(
            organization_id=self.organization.id,
            stack_key="sales-orders",
            match_key="PO-0000",
            substack_id=orders[0].id,
            attributes={},
        )
        item_record = Record(
            organization_id=self.organization.id,
            stack_key="items",
            match_key="BRACKET-A",
            substack_id=item.id,
            attributes={},
        )
        self.session.add_all([order_record, item_record])
        self.session.flush()
        self.session.add(
            RecordLink(
                organization_id=self.organization.id,
                from_kind="record",
                from_id=order_record.id,
                to_kind="record",
                to_id=item_record.id,
                relation_name="line_item",
            )
        )
        self.session.commit()

        response = self.client.get(
            f"/accounts/{self.organization.id}/clients/{client.id}/picture",
            params={"max_neighbours_per_node": 8},
        )
        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(body["subject"]["id"], str(client.id))
        self.assertEqual(body["caps"]["max_neighbours_per_node"], DEFAULT_MAX_NEIGHBOURS)
        # Subject + 8 orders (degree-capped); item only reachable via uncapped order.
        node_ids = {n["id"] for n in body["nodes"]}
        self.assertIn(str(client.id), node_ids)
        self.assertEqual(body["omitted_neighbours"].get(str(client.id)), 2)
        order_ids = {str(o.id) for o in orders}
        kept_orders = node_ids & order_ids
        self.assertEqual(len(kept_orders), 8)
        # Depth never exceeds 2.
        self.assertTrue(all(n["depth"] <= 2 for n in body["nodes"]))
        # Item appears only if its parent order survived the degree cap.
        if str(orders[0].id) in kept_orders:
            self.assertIn(str(item.id), node_ids)
        self.assertLessEqual(len(body["nodes"]), 50)

    def test_non_client_substack_returns_404(self):
        order = self._substack("sales-orders", "PO-1")
        self.session.commit()
        response = self.client.get(
            f"/accounts/{self.organization.id}/clients/{order.id}/picture"
        )
        self.assertEqual(404, response.status_code)

    def test_private_neighbour_hidden_from_other_member(self):
        client = self._substack("clients", "Shared Client")
        private_order = self._substack("sales-orders", "Secret PO", owner=self.alice.id)
        public_order = self._substack("sales-orders", "Open PO")
        self.session.add_all([
            SubstackLink(substack_id=client.id, related_substack_id=private_order.id, reason="customer_of"),
            SubstackLink(substack_id=client.id, related_substack_id=public_order.id, reason="customer_of"),
        ])
        self.session.commit()

        self.current_user = self.bob
        body = self.client.get(
            f"/accounts/{self.organization.id}/clients/{client.id}/picture"
        ).json()
        names = {n["name"] for n in body["nodes"]}
        self.assertIn("Open PO", names)
        self.assertNotIn("Secret PO", names)


if __name__ == "__main__":
    unittest.main()
