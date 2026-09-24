"""Propose facts from an ingested version; drop anything not verbatim in the text.

#92 Steps 4–5: a reader never writes a record — it returns a Proposal where every
value carries a quote that `find_exact` located in the source text. Unquotable
candidates are refused, never guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from .config import get_settings
from .extractions import ClientExtraction, ItemExtraction, SalesOrderExtraction
from .findings import create_finding
from .jobs import enqueue_job
from .models import Document, DocumentVersion, KnowledgeJob, WhatsappMessage

MODEL_VERSION = "propose.v1"

# Mirror filing.STACK_TYPE_FOR_SOURCE (avoid importing filing — circular with enqueue).
_SOURCE_STACK = {
    "google_drive": "files",
    "whatsapp": "conversations",
}

# Stack type -> extraction schema (feature-6 catalog not wired yet).
_EXTRACTION_SCHEMAS: dict[str, type[BaseModel]] = {
    "sales-orders": SalesOrderExtraction,
    "clients": ClientExtraction,
    "items": ItemExtraction,
}

_SKIP_SCHEMA_FIELDS = frozenset(
    {"report", "conflicts", "open_questions", "references", "line_items", "changes", "approvals"}
)


@dataclass(frozen=True)
class ProposedField:
    name: str
    value: str
    quote: str
    start: int
    end: int


@dataclass(frozen=True)
class Proposal:
    stack: str
    fields: list[ProposedField]
    read_by: tuple[str, str]
    document_version_id: UUID | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


def find_exact(text: str, quote: str) -> tuple[int, int] | None:
    """Return (start, end) when quote appears verbatim; None if invented or empty."""
    if not quote:
        return None
    start = text.find(quote)
    if start < 0:
        return None
    return start, start + len(quote)


def stack_fields(stack: str) -> list[str]:
    """Field names for a stack: extraction schema when known, else a tiny default."""
    schema = _EXTRACTION_SCHEMAS.get(stack)
    if schema is None:
        return ["summary"]
    return [
        name
        for name, info in schema.model_fields.items()
        if name not in _SKIP_SCHEMA_FIELDS and getattr(info.annotation, "__name__", "") != "list"
    ]


def classify(text: str, source: str | None = None) -> str:
    """Pick a Stack for this version. Prefer source filing map; else light heuristics."""
    if source and source in _SOURCE_STACK:
        # Drive files may still be sales orders; sniff before falling back to "files".
        if source == "google_drive":
            lower = text.lower()
            if re.search(r"\bpurchase\s+order\b", lower) or re.search(r"\bpo[\s#:-]*\d", lower):
                return "sales-orders"
            if re.search(r"\binvoice\b", lower):
                return "invoices"
        return _SOURCE_STACK[source]
    lower = text.lower()
    if re.search(r"\bpurchase\s+order\b", lower) or re.search(r"\bpo[\s#:-]*\d", lower):
        return "sales-orders"
    return "files"


def quotable_fields(text: str, candidates: list[dict[str, str]]) -> list[ProposedField]:
    """Keep only candidates whose quote is a verbatim substring of text."""
    fields: list[ProposedField] = []
    for item in candidates:
        quote = item.get("quote") or ""
        span = find_exact(text, quote)
        if span is None:
            continue
        value = item.get("value") or quote
        name = item.get("name") or "field"
        fields.append(ProposedField(name=name, value=value, quote=quote, start=span[0], end=span[1]))
    return fields


def rule_extract(text: str, fields: list[str]) -> list[dict[str, str]]:
    """Deterministic extractors for known PO patterns — no LLM required."""
    found: list[dict[str, str]] = []
    if "order_number" in fields:
        match = re.search(r"\b(?:PO|Purchase\s+Order)[\s#:.-]*([A-Z0-9][\w-]*)", text, re.IGNORECASE)
        if match:
            found.append({"name": "order_number", "value": match.group(1), "quote": match.group(0)})
    if "customer_name" in fields:
        match = re.search(r"(?:Buyer|Customer|Bill\s+To)\s*[:\-]\s*([^\n,]+)", text, re.IGNORECASE)
        if match:
            found.append(
                {"name": "customer_name", "value": match.group(1).strip(), "quote": match.group(0)}
            )
    if "quantity" in fields or "summary" in fields:
        match = re.search(r"\b(\d+)\s+(pcs|pieces|units|kg|boxes)\b", text, re.IGNORECASE)
        if match and "quantity" in fields:
            found.append({"name": "quantity", "value": match.group(1), "quote": match.group(0)})
    if "summary" in fields and text.strip():
        # First non-empty line as a quotable summary when no richer schema applies.
        line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if line:
            found.append({"name": "summary", "value": line[:200], "quote": line[:200]})
    return found


def llm_extract(text: str, stack: str) -> list[dict[str, str]]:
    """Ask the configured LLM for field+quote pairs; empty when OpenAI is unset."""
    settings = get_settings()
    if settings.openai_api_key is None:
        return []
    schema = _EXTRACTION_SCHEMAS.get(stack)
    if schema is None:
        return []
    try:
        from .llm import get_llm_client
        from .prompts import SYSTEM_POLICY

        client = get_llm_client()
        prompt = (
            f"{SYSTEM_POLICY}\n\nExtract fields for stack '{stack}'. "
            "Every non-empty value MUST include a verbatim quote from the evidence."
        )
        result = client.parse(prompt=prompt, evidence=text, schema=schema)
    except Exception:
        return []
    return _flatten_evidence_values(result.parsed.model_dump())


def _flatten_evidence_values(payload: Any, prefix: str = "") -> list[dict[str, str]]:
    """Walk an extraction dump into {name, value, quote} candidates."""
    out: list[dict[str, str]] = []
    if isinstance(payload, dict):
        if "value" in payload and payload.get("value"):
            citations = payload.get("citations") or []
            quote = citations[0] if citations else str(payload["value"])
            out.append({"name": prefix or "field", "value": str(payload["value"]), "quote": str(quote)})
            return out
        for key, value in payload.items():
            if key in _SKIP_SCHEMA_FIELDS and key != "line_items":
                continue
            name = f"{prefix}.{key}" if prefix else key
            out.extend(_flatten_evidence_values(value, name))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            name = f"{prefix}[{index}]" if prefix else str(index)
            out.extend(_flatten_evidence_values(item, name))
    return out


def propose_from_text(
    text: str,
    *,
    stack: str | None = None,
    source: str | None = None,
    document_version_id: UUID | None = None,
    evidence: dict[str, Any] | None = None,
    candidates: list[dict[str, str]] | None = None,
) -> Proposal:
    """Core reader: classify → extract → keep only verbatim quotes."""
    chosen = stack or classify(text, source)
    fields_wanted = stack_fields(chosen)
    if candidates is not None:
        raw = candidates
        reader = ("test", MODEL_VERSION)
    else:
        settings = get_settings()
        if settings.openai_api_key is not None:
            raw = llm_extract(text, chosen)
            reader = ("llm", settings.openai_model)
            if not raw:
                raw = rule_extract(text, fields_wanted)
                reader = ("rules", MODEL_VERSION)
        else:
            raw = rule_extract(text, fields_wanted)
            reader = ("rules", MODEL_VERSION)
    return Proposal(
        stack=chosen,
        fields=quotable_fields(text, raw),
        read_by=reader,
        document_version_id=document_version_id,
        evidence=evidence or {},
    )


def propose_from(
    version: DocumentVersion,
    session: Session | None = None,
    *,
    create_findings: bool = False,
) -> Proposal:
    """Propose from a stored document version; optionally open Finding rows for review."""
    document = session.get(Document, version.document_id) if session is not None else None
    source = document.source if document is not None else None
    proposal = propose_from_text(
        version.content,
        source=source,
        document_version_id=version.id,
        evidence={"document_version_id": str(version.id)},
    )
    if create_findings and session is not None and document is not None and proposal.fields:
        for item in proposal.fields:
            create_finding(
                session,
                organization_id=document.organization_id,
                check_key="propose.field",
                subject_kind="document_version",
                subject_id=version.id,
                summary_sentence=f"Proposed {item.name}: {item.value}",
                observed_value=item.value,
                evidence={
                    "quote": item.quote,
                    "location": {"start": item.start, "end": item.end},
                    "stack": proposal.stack,
                    "read_by": list(proposal.read_by),
                },
                owner_user_id=document.owner_user_id,
                fingerprint=f"{item.name}:{item.start}:{item.end}",
            )
    return proposal


def propose_from_message(msg: WhatsappMessage, session: Session | None = None) -> Proposal:
    """Reader for stored WhatsApp rows — WAHA and Cloud API share this hand-over."""
    text = (msg.body or "").strip()
    evidence = {
        "wa_message_id": msg.wa_message_id,
        "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
        "sender": msg.sender_name or msg.sender_jid,
        "from_me": msg.from_me,
    }
    return propose_from_text(text, stack="conversations", source="whatsapp", evidence=evidence)


def enqueue_propose_from(session: Session, version: DocumentVersion, document: Document) -> KnowledgeJob:
    """Queue propose_version after a new revision — same pattern as embed_version."""
    return enqueue_job(
        session,
        organization_id=document.organization_id,
        owner_user_id=document.owner_user_id,
        kind="propose_version",
        payload={"document_version_id": str(version.id)},
        dedupe_key=f"propose:{version.id}:{MODEL_VERSION}",
    )


def run_propose_version(session: Session, version_id: UUID) -> Proposal:
    version = session.get(DocumentVersion, version_id)
    if version is None:
        raise ValueError("document_version_not_found")
    return propose_from(version, session, create_findings=True)
