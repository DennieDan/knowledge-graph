"""Scoped neighbourhood walks over links (#99 Step 1).

A map answers one question at a time. Degree capping is a correctness
requirement: one hub node must not turn a 2-hop walk into the whole org.
Links-only — no layout library here.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import get_current_user
from .database import get_session
from .models import Record, RecordLink, Substack, SubstackLink, User

router = APIRouter(tags=["graph"])

DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_NODES = 50
DEFAULT_MAX_NEIGHBOURS = 8

# Kinds we can resolve to a Substack id for the client picture.
_SUBSTACK_KIND = "substack"
_RECORD_KIND = "record"


@dataclass(frozen=True)
class NeighbourEdge:
    neighbour_id: UUID
    relation: str
    source: str  # "substack_link" | "record_link"
    direction: str  # "out" | "in"


@dataclass
class WalkResult:
    node_ids: list[UUID]
    depths: dict[UUID, int]
    edges: list[tuple[UUID, UUID, str, str]]  # from, to, relation, source
    omitted_neighbours: dict[UUID, int] = field(default_factory=dict)
    truncated: bool = False


def _visible(user: User):
    return or_(Substack.owner_user_id.is_(None), Substack.owner_user_id == user.id)


def _node_json(substack: Substack, depth: int) -> dict:
    return {
        "id": str(substack.id),
        "type_id": substack.stack_type,
        "name": substack.name,
        "depth": depth,
    }


def collect_substack_neighbours(
    session: Session,
    organization_id: UUID,
    substack_ids: set[UUID],
) -> dict[UUID, list[NeighbourEdge]]:
    """Undirected adjacency for the given substack ids from both link tables."""
    neighbours: dict[UUID, list[NeighbourEdge]] = defaultdict(list)
    if not substack_ids:
        return neighbours

    for link in session.scalars(
        select(SubstackLink).where(
            or_(
                SubstackLink.substack_id.in_(substack_ids),
                SubstackLink.related_substack_id.in_(substack_ids),
            )
        )
    ).all():
        if link.substack_id in substack_ids:
            neighbours[link.substack_id].append(
                NeighbourEdge(
                    neighbour_id=link.related_substack_id,
                    relation=link.reason or "related",
                    source="substack_link",
                    direction="out",
                )
            )
        if link.related_substack_id in substack_ids:
            neighbours[link.related_substack_id].append(
                NeighbourEdge(
                    neighbour_id=link.substack_id,
                    relation=link.reason or "related",
                    source="substack_link",
                    direction="in",
                )
            )

    # Bridge records that hang off these substacks, then pull polymorphic edges.
    records = session.scalars(
        select(Record).where(
            Record.organization_id == organization_id,
            Record.substack_id.in_(substack_ids),
        )
    ).all()
    record_to_substack = {r.id: r.substack_id for r in records if r.substack_id is not None}
    record_ids = set(record_to_substack)
    if not record_ids and not substack_ids:
        return neighbours

    conditions = [
        (RecordLink.from_kind == _SUBSTACK_KIND) & RecordLink.from_id.in_(substack_ids),
        (RecordLink.to_kind == _SUBSTACK_KIND) & RecordLink.to_id.in_(substack_ids),
    ]
    if record_ids:
        conditions.extend([
            (RecordLink.from_kind == _RECORD_KIND) & RecordLink.from_id.in_(record_ids),
            (RecordLink.to_kind == _RECORD_KIND) & RecordLink.to_id.in_(record_ids),
        ])
    link_rows = session.scalars(
        select(RecordLink).where(
            RecordLink.organization_id == organization_id,
            or_(*conditions),
        )
    ).all()

    # Resolve every endpoint that might appear on a record_link to a substack id.
    needed_record_ids: set[UUID] = set()
    for link in link_rows:
        if link.from_kind == _RECORD_KIND:
            needed_record_ids.add(link.from_id)
        if link.to_kind == _RECORD_KIND:
            needed_record_ids.add(link.to_id)
    missing = needed_record_ids - record_to_substack.keys()
    if missing:
        for record in session.scalars(select(Record).where(Record.id.in_(missing))).all():
            if record.substack_id is not None:
                record_to_substack[record.id] = record.substack_id

    def resolve(kind: str, entity_id: UUID) -> UUID | None:
        if kind == _SUBSTACK_KIND:
            return entity_id
        if kind == _RECORD_KIND:
            return record_to_substack.get(entity_id)
        return None

    for link in link_rows:
        left = resolve(link.from_kind, link.from_id)
        right = resolve(link.to_kind, link.to_id)
        if left is None or right is None or left == right:
            continue
        if left in substack_ids:
            neighbours[left].append(
                NeighbourEdge(
                    neighbour_id=right,
                    relation=link.relation_name,
                    source="record_link",
                    direction="out",
                )
            )
        if right in substack_ids:
            neighbours[right].append(
                NeighbourEdge(
                    neighbour_id=left,
                    relation=link.relation_name,
                    source="record_link",
                    direction="in",
                )
            )

    return neighbours


def walk_neighbourhood(
    subject_id: UUID,
    adjacency: dict[UUID, list[NeighbourEdge]],
    *,
    readable: set[UUID],
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_neighbours_per_node: int = DEFAULT_MAX_NEIGHBOURS,
) -> WalkResult:
    """BFS with visited set, per-node degree cap, and node budget.

    Edges are kept only when the *destination* is readable — existence of an
    edge must not prove a record the viewer cannot read exists.
    """
    if subject_id not in readable:
        return WalkResult(node_ids=[], depths={}, edges=[])

    depths: dict[UUID, int] = {subject_id: 0}
    node_ids: list[UUID] = [subject_id]
    edges: list[tuple[UUID, UUID, str, str]] = []
    omitted: dict[UUID, int] = {}
    seen_edges: set[tuple[UUID, UUID, str, str]] = set()
    truncated = False

    queue: deque[UUID] = deque([subject_id])
    while queue:
        current = queue.popleft()
        depth = depths[current]
        if depth >= max_depth:
            continue

        raw = adjacency.get(current, [])
        # Stable order: by neighbour id so tests and UI do not shuffle.
        deduped: list[NeighbourEdge] = []
        seen_n: set[UUID] = set()
        for edge in sorted(raw, key=lambda e: (str(e.neighbour_id), e.relation, e.source)):
            if edge.neighbour_id in seen_n:
                continue
            seen_n.add(edge.neighbour_id)
            deduped.append(edge)

        kept = deduped[:max_neighbours_per_node]
        if len(deduped) > max_neighbours_per_node:
            omitted[current] = len(deduped) - max_neighbours_per_node

        for edge in kept:
            dest = edge.neighbour_id
            if dest not in readable:
                continue
            key = (current, dest, edge.relation, edge.source)
            rev = (dest, current, edge.relation, edge.source)
            if key in seen_edges or rev in seen_edges:
                continue
            seen_edges.add(key)
            edges.append(key)

            if dest in depths:
                continue
            if len(node_ids) >= max_nodes:
                truncated = True
                continue
            depths[dest] = depth + 1
            node_ids.append(dest)
            queue.append(dest)

    return WalkResult(
        node_ids=node_ids,
        depths=depths,
        edges=edges,
        omitted_neighbours=omitted,
        truncated=truncated,
    )


def build_client_picture(
    session: Session,
    user: User,
    organization_id: UUID,
    subject: Substack,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_neighbours_per_node: int = DEFAULT_MAX_NEIGHBOURS,
) -> dict:
    # Seed adjacency from the subject, then expand as we discover nodes so we
    # only load link rows for the frontier's organisation — not the whole DB.
    readable_rows = session.scalars(
        select(Substack).where(
            Substack.organization_id == organization_id,
            _visible(user),
        )
    ).all()
    readable = {row.id: row for row in readable_rows}
    if subject.id not in readable:
        raise HTTPException(status_code=404, detail="substack_not_found")

    known = {subject.id}
    adjacency: dict[UUID, list[NeighbourEdge]] = {}
    # Iteratively fetch neighbours for newly discovered nodes so record_links
    # that sit two hops out are still visible within max_depth.
    frontier = {subject.id}
    for _ in range(max_depth + 1):
        batch = collect_substack_neighbours(session, organization_id, frontier)
        for node_id, edges in batch.items():
            adjacency.setdefault(node_id, []).extend(edges)
            for edge in edges:
                if edge.neighbour_id in readable:
                    known.add(edge.neighbour_id)
        next_frontier = {
            edge.neighbour_id
            for edges in batch.values()
            for edge in edges
            if edge.neighbour_id in readable and edge.neighbour_id not in adjacency
        }
        if not next_frontier:
            break
        frontier = next_frontier

    walk = walk_neighbourhood(
        subject.id,
        adjacency,
        readable=set(readable),
        max_depth=max_depth,
        max_nodes=max_nodes,
        max_neighbours_per_node=max_neighbours_per_node,
    )

    nodes = [
        _node_json(readable[node_id], walk.depths[node_id])
        for node_id in walk.node_ids
        if node_id in readable
    ]
    return {
        "subject": _node_json(subject, 0),
        "nodes": nodes,
        "edges": [
            {
                "from_id": str(from_id),
                "to_id": str(to_id),
                "relation": relation,
                "source": source,
            }
            for from_id, to_id, relation, source in walk.edges
            if from_id in walk.depths and to_id in walk.depths
        ],
        "omitted_neighbours": {
            str(node_id): count for node_id, count in walk.omitted_neighbours.items()
        },
        "truncated": walk.truncated,
        "caps": {
            "max_depth": max_depth,
            "max_nodes": max_nodes,
            "max_neighbours_per_node": max_neighbours_per_node,
        },
    }


@router.get("/accounts/{organization_id}/clients/{substack_id}/picture")
def client_picture(
    organization_id: UUID,
    substack_id: UUID,
    max_depth: int = Query(DEFAULT_MAX_DEPTH, ge=0, le=2),
    max_nodes: int = Query(DEFAULT_MAX_NODES, ge=1, le=50),
    max_neighbours_per_node: int = Query(DEFAULT_MAX_NEIGHBOURS, ge=1, le=50),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Client substack + degree-capped linked neighbourhood (list-ready, no layout)."""
    membership_for(organization_id, user, session)
    subject = session.get(Substack, substack_id)
    if (
        subject is None
        or subject.organization_id != organization_id
        or subject.stack_type != "clients"
    ):
        raise HTTPException(status_code=404, detail="client_not_found")
    if subject.owner_user_id is not None and subject.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="client_not_found")

    return build_client_picture(
        session,
        user,
        organization_id,
        subject,
        max_depth=max_depth,
        max_nodes=max_nodes,
        max_neighbours_per_node=max_neighbours_per_node,
    )
