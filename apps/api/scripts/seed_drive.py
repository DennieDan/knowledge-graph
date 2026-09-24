"""Seed a real Google Drive with sample data for testing the knowledge base.

The app's OAuth grant is drive.readonly, so this script runs its own
localhost OAuth flow with the narrower drive.file scope (it can only see
files it creates). Tokens are cached in scripts/.seed_tokens.json.

Run from apps/api with the virtual environment active:

    python -m scripts.seed_drive --account studionorth
    python -m scripts.seed_drive --account personal
    python -m scripts.seed_drive --account studionorth --wipe

Each --account opens a browser once; sign in with the matching Google
account. Later runs reuse the cached token.

    studionorth  -> precision-engineering sample data (Studio North Workspace)
    personal     -> food-supply sample data (personal Gmail Drive)

Use --wipe to trash the previously created sample root folder first.

WhatsApp chats are not uploaded to Drive; they are real export files from
scripts/generate_whatsapp_exports.py, uploaded through the WhatsApp modal.
"""
import argparse
import base64
import csv
import html
import io
import json
import secrets
import struct
import sys
import threading
import webbrowser
import zlib
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
SCOPE = "https://www.googleapis.com/auth/drive.file"
TOKEN_CACHE = Path(__file__).parent / ".seed_tokens.json"

FOLDER_MIME = "application/vnd.google-apps.folder"
DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"

ROOT_NAMES = {
    "studionorth": "MK Sample - Precision Engineering",
    "personal": "MK Sample - Food Supply",
}


# ---------------------------------------------------------------- auth ----

def _run_oauth_flow(client_id: str, client_secret: str) -> dict:
    port = 8877
    server = HTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
    state = secrets.token_urlsafe(16)
    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            if query.get("state", [""])[0] != state:
                self.send_response(400)
                self.end_headers()
                return
            result["code"] = query.get("code", [""])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Authorized. You can close this tab and return to the terminal.")

        def log_message(self, *args):
            pass

    server.RequestHandlerClass = Handler
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    params = {
        "client_id": client_id,
        "redirect_uri": f"http://localhost:{port}/",
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent select_account",
        "state": state,
    }
    print(f"Opening browser for Google sign-in ({AUTH_URL}?...)")
    webbrowser.open(f"{AUTH_URL}?{urlencode(params)}")
    thread.join(timeout=180)
    server.server_close()
    if not result.get("code"):
        sys.exit("No authorization code received within 3 minutes.")

    resp = httpx.post(TOKEN_URL, data={
        "code": result["code"],
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": f"http://localhost:{port}/",
        "grant_type": "authorization_code",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_token(account: str) -> str:
    settings = get_settings()
    client_id = settings.google_client_id.get_secret_value()
    client_secret = settings.google_client_secret.get_secret_value()

    cache = json.loads(TOKEN_CACHE.read_text()) if TOKEN_CACHE.exists() else {}
    entry = cache.get(account, {})

    def save(token_json: dict):
        entry.update(token_json)
        cache[account] = entry
        TOKEN_CACHE.write_text(json.dumps(cache, indent=2))

    if entry.get("refresh_token"):
        resp = httpx.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "refresh_token": entry["refresh_token"],
            "client_id": client_id,
            "client_secret": client_secret,
        }, timeout=15)
        if resp.status_code == 200:
            token = resp.json()
            save(token)
            return token["access_token"]
        print("Cached token rejected; starting a fresh sign-in.")

    token = _run_oauth_flow(client_id, client_secret)
    if not token.get("refresh_token"):
        sys.exit("Google did not return a refresh token; cannot cache credentials.")
    save(token)
    return token["access_token"]


# ------------------------------------------------------------- drive ----

class Drive:
    def __init__(self, token: str):
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {token}"}, timeout=60)

    def _post(self, url: str, **kwargs) -> dict:
        resp = self.client.post(url, **kwargs)
        if resp.status_code >= 400:
            raise RuntimeError(f"Drive API {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def create_folder(self, name: str, parent: str | None = None) -> str:
        meta = {"name": name, "mimeType": FOLDER_MIME}
        if parent:
            meta["parents"] = [parent]
        return self._post(DRIVE_FILES, json=meta)["id"]

    def upload(self, name: str, content: bytes, mime: str,
               parent: str | None = None, convert_to: str | None = None) -> str:
        meta = {"name": name}
        if parent:
            meta["parents"] = [parent]
        if convert_to:
            meta["mimeType"] = convert_to
        boundary = "seed" + secrets.token_hex(8)
        body = b"\r\n".join([
            f"--{boundary}".encode(),
            b"Content-Type: application/json; charset=UTF-8",
            b"",
            json.dumps(meta).encode(),
            f"--{boundary}".encode(),
            f"Content-Type: {mime}".encode(),
            b"",
            content,
            f"--{boundary}--".encode(),
            b"",
        ])
        return self._post(
            DRIVE_UPLOAD,
            params={"uploadType": "multipart"},
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            content=body,
        )["id"]

    def find_child(self, name: str, parent: str | None = None) -> str | None:
        q = f"name = '{name}' and mimeType = '{FOLDER_MIME}' and trashed = false"
        if parent:
            q += f" and '{parent}' in parents"
        resp = self.client.get(DRIVE_FILES, params={"q": q, "fields": "files(id)"})
        files = resp.json().get("files", [])
        return files[0]["id"] if files else None

    def trash(self, file_id: str):
        self.client.patch(DRIVE_FILES + f"/{file_id}", json={"trashed": True})


# ---------------------------------------------------------- generators ----

def make_pdf(lines: list[str]) -> bytes:
    """Minimal multi-page text PDF, no dependencies."""
    per_page = 45
    pages = [lines[i:i + per_page] for i in range(0, len(lines), per_page)] or [[]]

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
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>")
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
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
              f"startxref\n{xref}\n%%EOF".encode())
    return out.getvalue()


def make_png(width: int = 400, height: int = 300) -> bytes:
    """Minimal PNG: grey 'scanned form' with darker band rows."""
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            band = 200 if (y // 24) % 2 else 235
            if x < 12 or y < 12 or x >= width - 12 or y >= height - 12:
                band = 120
            row += bytes([band, band, band])
        rows.append(bytes(row))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    raw = zlib.compress(b"".join(rows))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


def csv_bytes(rows: list[list]) -> bytes:
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode()


def doc_html(title: str, paragraphs: list[str]) -> bytes:
    body = "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
    return f"<h1>{html.escape(title)}</h1>{body}".encode()


def po_pdf(po_no: str, rev: str, buyer: str, seller: str, items: list[tuple],
           order_date: date, delivery_date: date, terms: str = "Net 30") -> bytes:
    lines = [
        f"PURCHASE ORDER  {po_no}  Revision {rev}",
        "",
        f"Buyer:    {buyer}",
        f"Seller:   {seller}",
        f"Order Date:    {order_date:%d %b %Y}",
        f"Required Delivery: {delivery_date:%d %b %Y}",
        f"Payment Terms: {terms}",
        "",
        f"{'Line':<5}{'Part No.':<16}{'Description':<42}{'Qty':>6}{'Unit Price':>12}",
        "-" * 82,
    ]
    total = 0.0
    for i, (part, desc, qty, price) in enumerate(items, 1):
        total += qty * price
        lines.append(f"{i:<5}{part:<16}{desc[:40]:<42}{qty:>6}{price:>12.2f}")
    lines += ["-" * 82, f"{'TOTAL (SGD)':>63}{total:>18.2f}", "",
              "Please acknowledge receipt and confirm delivery date.",
              f"Authorized: {buyer} Purchasing"]
    return make_pdf(lines)


def invoice_pdf(inv_no: str, po_no: str, seller: str, buyer: str,
                items: list[tuple], inv_date: date) -> bytes:
    lines = [
        f"TAX INVOICE  {inv_no}",
        "",
        f"From: {seller}", f"To:   {buyer}",
        f"Invoice Date: {inv_date:%d %b %Y}", f"Customer PO: {po_no}",
        "", f"{'Description':<50}{'Qty':>6}{'Amount':>12}", "-" * 70,
    ]
    subtotal = sum(q * p for _, q, p in items)
    gst = subtotal * 0.09
    for desc, q, p in items:
        lines.append(f"{desc[:48]:<50}{q:>6}{q * p:>12.2f}")
    lines += ["-" * 70, f"{'Subtotal':>56}{subtotal:>12.2f}",
              f"{'GST 9%':>56}{gst:>12.2f}", f"{'TOTAL DUE (SGD)':>56}{subtotal + gst:>12.2f}"]
    return make_pdf(lines)


def delivery_pdf(do_no: str, po_no: str, seller: str, buyer: str,
                 items: list[tuple], do_date: date, address: str) -> bytes:
    lines = [
        f"DELIVERY ORDER  {do_no}", "",
        f"From: {seller}", f"To:   {buyer}",
        f"Date: {do_date:%d %b %Y}", f"Reference PO: {po_no}",
        f"Deliver To: {address}", "", f"{'Description':<50}{'Qty':>6}", "-" * 58,
    ]
    for desc, q in items:
        lines.append(f"{desc[:48]:<50}{q:>6}")
    lines += ["", "Received by: ______________    Date: ____________"]
    return make_pdf(lines)


# ------------------------------------------------------------- datasets ----

def d(n: int) -> date:
    return date(2026, 8, 3) + timedelta(days=n * 5)


def build_precision_engineering() -> dict[str, list[tuple]]:
    """folder -> [(name, kind, payload)]; kind in pdf|doc|sheet|txt|png|csv"""
    seller = "Studio North Precision Pte Ltd"
    clients = [
        ("Meridian Aerospace Components Pte Ltd", "10 Seletar Aerospace View, Singapore 797565"),
        ("Semicon Dynamics Asia", "2 Kallang Sector, Singapore 349278"),
        ("MedFab Systems", "11 Biopolis Way, Singapore 138667"),
        ("Harbour Marine Engineering", "51 Tuas Bay Drive, Singapore 637308"),
    ]
    parts = [
        ("SN-1001", "Aluminium housing, CNC milled, anodized", 88.50),
        ("SN-1002", "Stainless shaft SS316, ground finish", 42.00),
        ("SN-1003", "Brass manifold block, 6-port", 120.75),
        ("SN-1004", "Titanium bracket Ti-6Al-4V", 210.00),
        ("SN-1005", "Delrin insulator bushing", 12.30),
        ("SN-1006", "Steel base plate, zinc plated", 65.40),
    ]
    folders: dict[str, list[tuple]] = {k: [] for k in [
        "Clients", "Sales Orders", "Specifications", "Supplier Orders",
        "Delivery Orders", "Invoices", "Price Lists", "Meetings",
        "Scanned Forms"]}

    for name, addr in clients:
        folders["Clients"].append((f"Client Profile - {name}", "doc",
            doc_html(name, [
                f"Address: {addr}",
                "Payment terms: Net 30. GST registered.",
                "Primary contact: procurement team via email; urgent changes via WhatsApp.",
                "Account notes: requires Certificate of Conformance with every delivery; "
                "PO revisions must be acknowledged within 1 working day.",
            ])))

    folders["Price Lists"].append(("Material Price List 2026", "sheet", csv_bytes([
        ["Material", "Grade", "Unit", "Price (SGD)", "Lead Time (days)"],
        ["Aluminium 6061-T6", "AMS 4027", "kg", "8.20", "7"],
        ["Stainless Steel 316", "ASTM A276", "kg", "11.50", "10"],
        ["Brass C360", "ASTM B16", "kg", "14.80", "14"],
        ["Titanium Ti-6Al-4V", "AMS 4911", "kg", "95.00", "21"],
        ["Delrin POM-C", "-", "kg", "6.10", "5"],
    ])))
    folders["Price Lists"].append(("Part Price List - Meridian Aerospace", "sheet", csv_bytes([
        ["Part No.", "Description", "Unit Price (SGD)", "MOQ"],
    ] + [[p, dsc, f"{pr:.2f}", "10"] for p, dsc, pr in parts])))

    for i, (part, desc, price) in enumerate(parts):
        rev = "B" if i % 3 == 0 else "A"
        folders["Specifications"].append((f"Spec {part} Rev {rev}", "doc",
            doc_html(f"{part} — {desc}", [
                f"Drawing: {part}-DWG Rev {rev}. Tolerance ISO 2768-mK unless noted.",
                f"Material per price list entry; surface finish Ra 1.6 unless otherwise specified.",
                f"Revision history: Rev A initial release (Jan 2026); "
                + (f"Rev B widened bore tolerance +0.05/-0.00 after Meridiam FA review." if rev == "B" else "Rev A current."),
                "Inspection: CMM report required for first article and every 500 pcs.",
            ])))

    suppliers = [
        "Singmet Alloys Pte Ltd", "FastenPro Hardware", "Anodize-It Surface Treatment",
        "Tuas Tooling & Dies", "PolyFab Engineering Plastics",
    ]
    for i, sup in enumerate(suppliers):
        folders["Supplier Orders"].append((f"SPO-{2600 + i} {sup}.pdf", "pdf",
            po_pdf(f"SPO-{2600 + i}", "A", seller, sup,
                   [(f"MAT-{100 + i}", f"Raw material / consumable for {sup}", 50 + i * 20, 9.75 + i)],
                   d(i), d(i) + timedelta(days=14), terms="Net 45")))

    po_counter = 4120
    deliveries = []
    for i in range(12):
        client, addr = clients[i % len(clients)]
        po_no = f"{client.split()[0].upper()[:3]}-PO-{po_counter + i}"
        items = [(parts[(i + j) % len(parts)][0], parts[(i + j) % len(parts)][1],
                  20 + j * 15 + i, parts[(i + j) % len(parts)][2]) for j in range(1 + i % 3)]
        rev = "B" if i % 4 == 3 else "A"
        folders["Sales Orders"].append((f"{po_no} Rev {rev}.pdf", "pdf",
            po_pdf(po_no, rev, client, seller, items, d(i), d(i) + timedelta(days=21))))
        if rev == "B":
            folders["Sales Orders"].append((f"{po_no} Rev A.pdf", "pdf",
                po_pdf(po_no, "A", client, seller, items[:1], d(i), d(i) + timedelta(days=21))))
        if i % 2 == 0:
            deliveries.append((f"DO-{7300 + i} for {po_no}.pdf", "pdf",
                delivery_pdf(f"DO-{7300 + i}", po_no, seller, client,
                             [(desc, q) for _, desc, q, _ in items], d(i) + timedelta(days=21), addr)))
            deliveries.append((f"INV-{9100 + i} for {po_no}.pdf", "pdf",
                invoice_pdf(f"INV-{9100 + i}", po_no, seller, client,
                            [(desc, q, p) for _, desc, q, p in items], d(i) + timedelta(days=23))))
    folders["Delivery Orders"] = deliveries[0::2]
    folders["Invoices"] = deliveries[1::2]

    # Golden v1 (#106): eight planted conflicts (see tests/fixtures/verdicts.json).
    # Chats name only Drive-backed POs, except C5 (order mentioned before it exists).
    folders["Meetings"] = [
        ("Meeting Notes - Meridian Q3 review", "doc", doc_html(
            # C8: deliberate client-name misspelling "Meridiam" (not Meridian).
            "Meridiam Q3 Review — 14 Aug 2026", [
                "Attendees: Studio North PM, Meridiam procurement lead.",
                "Action: Meridian to consolidate SN-1001 orders into monthly releases.",
                "Action: Studio North to quote titanium bracket SN-1004 with Rev C drawing by 28 Aug.",
                "Concern raised on DO-7300 late delivery; root cause was anodizing backlog."])),
        ("Meeting Notes - Production planning wk36", "doc", doc_html(
            "Production Planning — Week 36", [
                "SN-1002 shafts: outsource grinding to Tuas Tooling while grinder spindle is repaired.",
                "Prioritize Semicon Dynamics order; delivery moved forward per WhatsApp confirmation.",
                "PICs: machining — Wei Ming; QC — Priya; purchasing — Linh."])),
        ("Meeting Notes - MedFab NPI kickoff", "doc", doc_html(
            "MedFab New Product Introduction Kickoff", [
                "MedFab requests first article of SN-1005 bushing with full CMM report.",
                "Target FAI submission 18 Sep 2026; PO expected after FA approval."])),
        ("Meeting Notes - Supplier review Singmet", "doc", doc_html(
            "Singmet Alloys Quarterly Review", [
                "Lead time slipped to 10 days on 316 bar; negotiate consignment stock for SN-1002.",
                "Price hold agreed through Q4 2026."])),
    ]

    folders["Scanned Forms"] = [
        ("Scanned PO - Harbour Marine HAR-PO-4131.png", "png", make_png()),
        ("Scanned Delivery Note - MedFab.png", "png", make_png(400, 340)),
    ]
    return folders


def build_food_supply() -> dict[str, list[tuple]]:
    seller = "Hoa Phuong Do Fresh Supply"
    clients = [
        ("The Marina Table Restaurant", "8 Raffles Quay, Singapore 048582"),
        ("Golden Wok Catering", "14 Defu Lane 10, Singapore 539195"),
        ("Azure Sky Hotel F&B", "3 Sentosa Gateway, Singapore 098544"),
        ("Little Saigon Bistro", "212 East Coast Road, Singapore 428914"),
    ]
    goods = [
        ("Veg", "Baby spinach 500g pack", 6.80), ("Veg", "Romaine lettuce head", 3.20),
        ("Sea", "Tiger prawns 21/25 1kg", 28.50), ("Sea", "Barramundi fillet 200g", 9.90),
        ("Meat", "Chicken breast boneless 2kg", 16.40), ("Dry", "Jasmine rice 25kg sack", 42.00),
        ("Dry", "Cooking oil 17L tin", 58.00), ("Veg", "Cherry tomatoes 250g", 4.60),
    ]
    folders: dict[str, list[tuple]] = {k: [] for k in [
        "Clients", "Sales Orders", "Supplier Orders", "Delivery Orders",
        "Invoices", "Price Lists", "Meetings", "Scanned Forms"]}

    for name, addr in clients:
        folders["Clients"].append((f"Client Profile - {name}", "doc",
            doc_html(name, [
                f"Delivery address: {addr}",
                "Ordering pattern: WhatsApp orders daily before 6pm for next-day delivery.",
                "Payment terms: Net 14. Halal certification required on poultry items.",
                "Standing order noted below; variations confirmed in chat.",
            ])))

    folders["Price Lists"].append(("Fresh Produce Price List Sep 2026", "sheet", csv_bytes([
        ["SKU", "Item", "Unit", "Price (SGD)", "Availability"],
    ] + [[f"{cat}-{100 + i}", item, "ea", f"{p:.2f}", "Daily"]
          for i, (cat, item, p) in enumerate(goods)])))

    for i in range(14):
        client, addr = clients[i % len(clients)]
        po_no = f"PO-{5500 + i}"
        items = [goods[(i + j) % len(goods)] for j in range(1 + i % 3)]
        line_items = [(f"{it[0]}-{100 + goods.index(it)}", it[1], 4 + j * 3 + i, it[2])
                      for j, it in enumerate(items)]
        folders["Sales Orders"].append((f"{po_no} {client}.pdf", "pdf",
            po_pdf(po_no, "A", client, seller, line_items, d(i // 2), d(i // 2) + timedelta(days=1),
                   terms="Net 14")))
        if i % 3 == 0:
            folders["Delivery Orders"].append((f"DO-{6600 + i} {client}.pdf", "pdf",
                delivery_pdf(f"DO-{6600 + i}", po_no, seller, client,
                             [(li[1], li[2]) for li in line_items], d(i // 2) + timedelta(days=1), addr)))
            folders["Invoices"].append((f"INV-{7700 + i} {client}.pdf", "pdf",
                invoice_pdf(f"INV-{7700 + i}", po_no, seller, client,
                            [(li[1], li[2], li[3]) for li in line_items], d(i // 2) + timedelta(days=3))))

    for i, sup in enumerate(["Kranji Farm Collective", "Jurong Fishery Port Supplier",
                             "Soon Huat Poultry", "Dry Goods Trading Co"]):
        folders["Supplier Orders"].append((f"SPO-{8800 + i} {sup}.pdf", "pdf",
            po_pdf(f"SPO-{8800 + i}", "A", seller, sup,
                   [(f"SUP-{i}", f"Bulk order — {sup}", 30 + i * 10, 120.0 + i * 35)],
                   d(i), d(i) + timedelta(days=2), terms="COD")))

    folders["Meetings"] = [
        ("Meeting Notes - Azure Sky contract review", "doc", doc_html(
            "Azure Sky Hotel Contract Review — 20 Aug 2026", [
                "Hotel wants fixed pricing on seafood through December despite market fluctuation.",
                "Agreed to weekly standing order with 20% flex, changes by Wednesday noon.",
                "Action: send updated spec sheet for barramundi portion sizing."])),
        ("Meeting Notes - Weekly ops sync", "doc", doc_html(
            "Weekly Ops Sync", [
                "Cold chain van 2 serviced; back in rotation Monday.",
                "Golden Wok complained about bruised tomatoes — QC to photograph each crate before dispatch.",
                "PICs: procurement — Phuong; deliveries — Daniel; QC — Mei."])),
    ]

    folders["Scanned Forms"] = [
        ("Scanned Order Form - Azure Sky.png", "png", make_png()),
        ("Scanned Credit Note Request.png", "png", make_png(400, 320)),
    ]
    return folders


# ----------------------------------------------------------------- main ----

def seed(drive: Drive, account: str, wipe: bool):
    root_name = ROOT_NAMES[account]
    existing = drive.find_child(root_name)
    if existing and wipe:
        print(f"Trashing existing '{root_name}' ({existing})")
        drive.trash(existing)
        existing = None
    root = existing or drive.create_folder(root_name)
    print(f"Root folder '{root_name}': https://drive.google.com/drive/folders/{root}")

    dataset = build_precision_engineering() if account == "studionorth" else build_food_supply()
    total = sum(len(v) for v in dataset.values())
    done = 0
    for folder_name, files in dataset.items():
        folder_id = drive.create_folder(folder_name, root)
        for name, kind, payload in files:
            if kind == "pdf":
                drive.upload(name, payload, "application/pdf", folder_id)
            elif kind == "doc":
                drive.upload(name, payload, "text/html", folder_id, convert_to=DOC_MIME)
            elif kind == "sheet":
                drive.upload(name, payload, "text/csv", folder_id, convert_to=SHEET_MIME)
            elif kind == "png":
                drive.upload(name, payload, "image/png", folder_id)
            else:
                drive.upload(name, payload, "text/plain", folder_id)
            done += 1
            print(f"  [{done}/{total}] {folder_name}/{name}")
    print(f"Done: {total} files in '{root_name}'.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--account", choices=sorted(ROOT_NAMES), required=True)
    parser.add_argument("--wipe", action="store_true",
                        help="trash the existing sample root folder first")
    args = parser.parse_args()
    seed(Drive(get_token(args.account)), args.account, args.wipe)


if __name__ == "__main__":
    main()
