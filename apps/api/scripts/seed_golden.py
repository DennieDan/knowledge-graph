"""Golden v1 seed consistency helpers (#106).

Drive seeding still runs via ``python -m scripts.seed_drive``. This module
checks that invented chat transcripts agree with Sales Order file names —
except the deliberate C5 absence (order mentioned before it exists).

Does not cut live golden v1 (no Drive wipe, no WhatsApp send, no tag).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.seed_drive import build_precision_engineering  # noqa: E402

# Order ids that chats may name even though no Sales Orders PDF exists yet (C5).
PLANTED_ABSENT_ORDERS = frozenset({"PO-4132"})

PO_IN_CHAT = re.compile(r"\b(?:[A-Z]{3}-)?PO-\d{4}\b")


def sales_order_po_numbers(folders: dict[str, list[tuple]]) -> set[str]:
    found: set[str] = set()
    for name, _kind, _payload in folders.get("Sales Orders", []):
        match = re.search(r"([A-Z]{3}-PO-\d+)", name)
        if match:
            found.add(match.group(1))
    return found


def chat_po_mentions(folders: dict[str, list[tuple]]) -> set[str]:
    found: set[str] = set()
    for _name, kind, payload in folders.get("Conversations", []):
        if kind != "txt":
            continue
        text = payload.decode() if isinstance(payload, (bytes, bytearray)) else str(payload)
        found.update(PO_IN_CHAT.findall(text))
    return found


def mention_resolved(mention: str, on_drive: set[str]) -> bool:
    """True if the chat mention matches a Drive PO (or is a planted absence)."""
    if mention in PLANTED_ABSENT_ORDERS:
        return True
    if mention in on_drive:
        return True
    # Bare PO-4121 matches SEM-PO-4121
    if mention.startswith("PO-") and any(po.endswith(mention) for po in on_drive):
        return True
    return False


def assert_chat_drive_agreement(folders: dict[str, list[tuple]] | None = None) -> None:
    """Raise AssertionError if a chat names a PO that Drive does not hold (except C5)."""
    folders = folders or build_precision_engineering()
    on_drive = sales_order_po_numbers(folders)
    stray = sorted(
        mention for mention in chat_po_mentions(folders) if not mention_resolved(mention, on_drive)
    )
    if stray:
        raise AssertionError(
            f"Chat PO mentions missing from Sales Orders (not in planted-absent set): {stray}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate Studio North chat ↔ Drive PO agreement (no network)",
    )
    args = parser.parse_args()
    if not args.check:
        parser.print_help()
        print("\nFLAG: live golden cut (Drive provision, WhatsApp send, tag) is not done.")
        return 0
    folders = build_precision_engineering()
    assert_chat_drive_agreement(folders)
    orders = sorted(sales_order_po_numbers(folders))
    chats = sorted(chat_po_mentions(folders))
    print(f"Sales order POs ({len(orders)}): {', '.join(orders)}")
    print(f"Chat PO mentions ({len(chats)}): {', '.join(chats)}")
    print("OK: chat ↔ Drive agreement (C5 PO-4132 allowed absent).")
    print("FLAG: live golden cut not done — invented transcript fixtures only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
