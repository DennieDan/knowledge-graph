"""Industry stack profiles for onboarding (#97 Step 1).

Catalogue rows only. Event-organiser keys live here and must not be added to
substack STACK_TYPES — those remain the supplier record types.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import STACK_TYPES

# Human names aligned with apps/web/app/lib/stacks.ts
SUPPLIER_STACK_NAMES: dict[str, str] = {
    "sales-orders": "Sales Orders",
    "clients": "Clients",
    "items": "Items",
    "invoices": "Invoices",
    "suppliers": "Suppliers",
    "supplier-orders": "Supplier Orders",
    "production-jobs": "Production Jobs",
    "specifications": "Specifications & Revisions",
    "conversations": "Conversations",
    "pics": "PICs",
    "meetings": "Meetings",
    "files": "Files",
}


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    value_type: str  # text | numeric | date | bool
    required: bool = False
    meaning: str | None = None
    searchable: bool = False


@dataclass(frozen=True)
class StackDef:
    key: str
    name: str
    fields: tuple[FieldDef, ...]
    parent_key: str | None = None


def _field(
    key: str,
    label: str,
    value_type: str,
    *,
    required: bool = False,
    meaning: str | None = None,
    searchable: bool = False,
) -> FieldDef:
    return FieldDef(
        key=key,
        label=label,
        value_type=value_type,
        required=required,
        meaning=meaning,
        searchable=searchable,
    )


SALES_ORDER_FIELDS: tuple[FieldDef, ...] = (
    _field("order_number", "Order number", "text", required=True, searchable=True, meaning="Customer PO or sales order reference"),
    _field("revision", "Revision", "text", meaning="Document revision letter or number"),
    _field("quantity", "Quantity", "numeric", required=True, meaning="Ordered quantity"),
    _field("unit_price", "Unit price", "numeric", meaning="Price per unit before tax"),
    _field("due_date", "Due date", "date", meaning="Requested delivery or completion date"),
)

# Minimal 1–2 fields for non-sales-order supplier stacks.
_SUPPLIER_MINIMAL: dict[str, tuple[FieldDef, ...]] = {
    "clients": (
        _field("company_name", "Company name", "text", required=True, searchable=True),
        _field("account_code", "Account code", "text", searchable=True),
    ),
    "items": (
        _field("sku", "SKU", "text", required=True, searchable=True),
        _field("description", "Description", "text"),
    ),
    "invoices": (
        _field("invoice_number", "Invoice number", "text", required=True, searchable=True),
        _field("amount", "Amount", "numeric"),
    ),
    "suppliers": (
        _field("vendor_name", "Vendor name", "text", required=True, searchable=True),
        _field("lead_time_days", "Lead time (days)", "numeric"),
    ),
    "supplier-orders": (
        _field("po_number", "PO number", "text", required=True, searchable=True),
        _field("ordered_at", "Ordered at", "date"),
    ),
    "production-jobs": (
        _field("job_number", "Job number", "text", required=True, searchable=True),
        _field("status", "Status", "text"),
    ),
    "specifications": (
        _field("drawing_number", "Drawing number", "text", required=True, searchable=True),
        _field("revision", "Revision", "text"),
    ),
    "conversations": (
        _field("channel", "Channel", "text", meaning="WhatsApp, email, or other"),
        _field("subject", "Subject", "text", searchable=True),
    ),
    "pics": (
        _field("person_name", "Person name", "text", required=True, searchable=True),
        _field("role", "Role", "text"),
    ),
    "meetings": (
        _field("title", "Title", "text", required=True, searchable=True),
        _field("held_at", "Held at", "date"),
    ),
    "files": (
        _field("file_name", "File name", "text", required=True, searchable=True),
        _field("mime_type", "MIME type", "text"),
    ),
}


def _supplier_stacks() -> tuple[StackDef, ...]:
    stacks: list[StackDef] = []
    for key in STACK_TYPES:
        if key == "sales-orders":
            fields = SALES_ORDER_FIELDS
        else:
            fields = _SUPPLIER_MINIMAL[key]
        stacks.append(StackDef(key=key, name=SUPPLIER_STACK_NAMES[key], fields=fields))
    return tuple(stacks)


# Invented event-organiser catalogue only — keys are not in substack STACK_TYPES.
_EVENT_ORGANISER_STACKS: tuple[StackDef, ...] = (
    StackDef(
        key="clients",
        name="Clients",
        fields=(
            _field("company_name", "Company name", "text", required=True, searchable=True),
            _field("contact_email", "Contact email", "text"),
        ),
    ),
    StackDef(
        key="events",
        name="Events",
        fields=(
            _field("event_name", "Event name", "text", required=True, searchable=True),
            _field("event_date", "Event date", "date", required=True),
        ),
    ),
    StackDef(
        key="meetings",
        name="Meetings",
        fields=(
            _field("title", "Title", "text", required=True, searchable=True),
            _field("held_at", "Held at", "date"),
        ),
    ),
    StackDef(
        key="vendors",
        name="Vendors",
        fields=(
            _field("vendor_name", "Vendor name", "text", required=True, searchable=True),
            _field("service_type", "Service type", "text"),
        ),
    ),
    StackDef(
        key="contacts",
        name="Contacts",
        fields=(
            _field("full_name", "Full name", "text", required=True, searchable=True),
            _field("phone", "Phone", "text"),
        ),
    ),
    StackDef(
        key="proposals",
        name="Proposals",
        fields=(
            _field("proposal_number", "Proposal number", "text", required=True, searchable=True),
            _field("total_amount", "Total amount", "numeric"),
        ),
    ),
    StackDef(
        key="finance-documents",
        name="Finance Documents",
        fields=(
            _field("document_number", "Document number", "text", required=True, searchable=True),
            _field("amount", "Amount", "numeric"),
        ),
    ),
    StackDef(
        key="conversations",
        name="Conversations",
        fields=(
            _field("channel", "Channel", "text"),
            _field("subject", "Subject", "text", searchable=True),
        ),
    ),
    StackDef(
        key="crew",
        name="Crew",
        fields=(
            _field("person_name", "Person name", "text", required=True, searchable=True),
            _field("role", "Role", "text"),
        ),
    ),
    StackDef(
        key="licenses",
        name="Licenses",
        fields=(
            _field("license_name", "License name", "text", required=True, searchable=True),
            _field("expires_on", "Expires on", "date"),
        ),
    ),
    StackDef(
        key="venues",
        name="Venues",
        fields=(
            _field("venue_name", "Venue name", "text", required=True, searchable=True),
            _field("capacity", "Capacity", "numeric"),
        ),
    ),
)


INDUSTRY_PROFILES: dict[str, tuple[StackDef, ...]] = {
    "supplier": _supplier_stacks(),
    "event_organiser": _EVENT_ORGANISER_STACKS,
}

DEFAULT_PROFILE_KEY = "supplier"


def get_profile(key: str) -> tuple[StackDef, ...] | None:
    return INDUSTRY_PROFILES.get(key)
