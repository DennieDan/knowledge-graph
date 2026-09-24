"""Typed claim storage + capped searchable promotion (#97 Step 2).

Claims already store value_text | value_numeric | value_date | value_bool with
value_type (see 0016_records_claims). Searchable catalogue fields may be
promoted onto records as generated columns so filters get real planner stats.

Unbounded searchable definitions must not become unbounded columns — cap hard.
"""
from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable

# Hard cap: mature products limit definitions that become real columns.
MAX_SEARCHABLE_PROMOTED = 8

# Allowlist order (first N that are also marked searchable get promoted).
# Aligns with supplier industry profile keys that are filtered/joined often.
PROMOTED_SEARCHABLE_KEYS: tuple[str, ...] = (
    "order_number",
    "company_name",
    "sku",
    "invoice_number",
    "po_number",
    "job_number",
    "drawing_number",
    "file_name",
)

assert len(PROMOTED_SEARCHABLE_KEYS) == MAX_SEARCHABLE_PROMOTED


@runtime_checkable
class SearchableFieldLike(Protocol):
    key: str
    searchable: bool


def searchable_keys_to_promote(
    fields: Iterable[SearchableFieldLike],
    *,
    cap: int = MAX_SEARCHABLE_PROMOTED,
    allowlist: tuple[str, ...] = PROMOTED_SEARCHABLE_KEYS,
) -> list[str]:
    """Return searchable field keys eligible for generated columns, capped.

    Prefer allowlist order, then any remaining searchable keys, truncated to cap.
    """
    searchable = {f.key for f in fields if f.searchable}
    ordered: list[str] = []
    for key in allowlist:
        if key in searchable and key not in ordered:
            ordered.append(key)
        if len(ordered) >= cap:
            return ordered
    for key in sorted(searchable):
        if key not in ordered:
            ordered.append(key)
        if len(ordered) >= cap:
            break
    return ordered
