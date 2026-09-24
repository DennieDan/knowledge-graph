"""Parser for WhatsApp "Export chat" files.

iOS shares a `WhatsApp Chat - <name>.zip` holding `_chat.txt`; Android shares
`WhatsApp Chat with <name>.txt` (or a .zip of it when media is included).
Lines look like:

    iOS      [24/9/26, 9:14:03 AM] Jon Tan: text
    Android  24/09/2026, 9:14 am - Jon Tan: text

Date order, 12/24-hour clock, separators, and U+200E / U+202F marks vary by
device and locale; the export carries device-local time with no offset.
"""
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath

DEFAULT_TZ = timezone(timedelta(hours=8))  # Singapore, no DST
MAX_TEXT_BYTES = 20 * 1024 * 1024
MAX_MESSAGES = 20_000

LRM = "\u200e"
_SPACES = str.maketrans({"\u202f": " ", "\u00a0": " ", "\u2009": " "})
_BIDI = str.maketrans("", "", "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2068\u2069")
_DATE = r"(?P<date>\d{1,4}[./-]\d{1,2}[./-]\d{1,4})"
_TIME = r"(?P<time>\d{1,2}[:.]\d{2}(?:[:.]\d{2})?)(?:\s?(?P<ampm>[AaPp]\.?\s?[Mm]\.?))?"
IOS_LINE = re.compile(rf"^\[{_DATE},?\s{_TIME}\]\s(?P<rest>.*)$")
ANDROID_LINE = re.compile(rf"^{_DATE},?\s{_TIME}\s[-\u2013]\s(?P<rest>.*)$")
CHAT_FILENAME = re.compile(r"^WhatsApp Chat (?:with |- )(?P<name>.+?)(?:\.txt|\.zip)?$", re.IGNORECASE)

EDITED = re.compile(r"\s*<This message was edited>$")
ATTACHED = re.compile(r"^<attached:\s*(?P<file>[^>]+)>\s*(?P<caption>[\s\S]*)$")
FILE_ATTACHED = re.compile(r"^(?P<file>[^\n]+?)\s\(file attached\)\s*(?P<caption>[\s\S]*)$")
OMITTED = re.compile(
    r"^(?:(?P<file>[^\n]+?)\s\u2022\s[^\n]*?\s)?(?P<kind>image|video|audio|sticker|GIF|document|Contact card|video note) omitted$",
    re.IGNORECASE,
)
DELETED = {"this message was deleted", "you deleted this message"}
GROUP_EVENT = re.compile(r"created group|created this group|\badded\b", re.IGNORECASE)
OMITTED_KIND = {"image": "image", "video": "video", "video note": "video", "gif": "video", "audio": "audio",
                "sticker": "sticker", "document": "document", "contact card": "vcard"}


class ExportFormatError(ValueError):
    pass


@dataclass
class ParsedMessage:
    wa_message_id: str
    sent_at: datetime
    sender: str
    body: str | None
    msg_type: str
    has_media: bool
    from_me: bool
    edited: bool
    line_format: str


@dataclass
class ParsedChat:
    name: str
    chat_type: str
    export_format: str
    participants: list[str]
    me_name: str | None
    messages: list[ParsedMessage] = field(default_factory=list)


def _media_type(filename: str) -> str:
    upper = filename.upper()
    suffix = PurePosixPath(filename).suffix.lower()
    if "STICKER" in upper or upper.startswith("STK-"):
        return "sticker"
    if "PHOTO" in upper or upper.startswith("IMG-") or suffix in {".jpg", ".jpeg", ".png", ".heic", ".webp"}:
        return "image"
    if "VIDEO" in upper or upper.startswith("VID-") or suffix in {".mp4", ".mov", ".3gp"}:
        return "video"
    if "AUDIO" in upper or upper.startswith(("PTT-", "AUD-")) or suffix in {".opus", ".m4a", ".mp3", ".aac"}:
        return "audio"
    return "document"


def _document_name(filename: str) -> str:
    return re.sub(r"^\d{8}-", "", filename.strip())


def _classify(text: str) -> tuple[str, str | None, bool, bool] | None:
    """(msg_type, body, has_media, edited) for a message body, or None for a system line."""
    special = text.startswith(LRM)
    clean = text.translate(_BIDI).strip()
    edited = bool(EDITED.search(clean))
    clean = EDITED.sub("", clean)
    if clean.casefold().rstrip(".") in DELETED:
        return "revoked", None, False, edited
    if clean.casefold() in {"<media omitted>", "null"}:
        return "media", None, True, edited
    for pattern in (ATTACHED, FILE_ATTACHED):
        match = pattern.match(clean)
        if match:
            kind = _media_type(match["file"])
            caption = match["caption"].strip() or None
            body = caption or (f"[document] {_document_name(match['file'])}" if kind == "document" else None)
            return kind, body, True, edited
    match = OMITTED.match(clean)
    if match:
        kind = OMITTED_KIND[match["kind"].casefold()]
        return kind, f"[{kind}] {match['file'].strip()}" if match["file"] else None, True, edited
    if special:
        return None
    return "chat", clean or None, False, edited


def _date_order(dates: list[str]) -> str:
    parts = [re.split(r"[./-]", d) for d in dates]
    if any(len(p[0]) == 4 for p in parts):
        return "ymd"
    if any(int(p[0]) > 12 for p in parts):
        return "dmy"
    if any(int(p[1]) > 12 for p in parts):
        return "mdy"
    return "dmy"


def _timestamp(date: str, time: str, ampm: str | None, order: str, tz: timezone) -> datetime:
    a, b, c = (int(x) for x in re.split(r"[./-]", date))
    year, month, day = {"ymd": (a, b, c), "dmy": (c, b, a), "mdy": (c, a, b)}[order]
    if year < 100:
        year += 2000
    clock = [int(x) for x in re.split(r"[:.]", time)]
    hour, minute, second = clock[0], clock[1], clock[2] if len(clock) > 2 else 0
    if ampm:
        pm = ampm.strip().lower().startswith("p")
        hour = hour % 12 + (12 if pm else 0)
    return datetime(year, month, day, hour, minute, second, tzinfo=tz).astimezone(timezone.utc)


def _message_id(sent_at: datetime, sender: str, body: str, ordinal: int) -> str:
    digest = hashlib.sha1(f"{sent_at.isoformat()}|{sender}|{body}|{ordinal}".encode()).hexdigest()
    return f"export_{digest[:24]}"


def chat_name_from_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    match = CHAT_FILENAME.match(PurePosixPath(filename).name)
    return match["name"].strip() if match else None


def parse_export_text(
    text: str,
    *,
    filename: str | None = None,
    me_name: str | None = None,
    tz: timezone = DEFAULT_TZ,
) -> ParsedChat:
    entries: list[list[str]] = []
    for line in text.translate(_SPACES).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        probe = line.lstrip(LRM)
        fmt, match = "ios", IOS_LINE.match(probe)
        if match is None:
            fmt, match = "android", ANDROID_LINE.match(probe)
        if match is not None:
            entries.append([fmt, match["date"], match["time"], match["ampm"] or "", match["rest"]])
        elif entries:
            entries[-1][4] += "\n" + line
    if not entries:
        raise ExportFormatError("not_a_whatsapp_export")
    if len(entries) > MAX_MESSAGES:
        raise ExportFormatError("export_too_large")

    order = _date_order([entry[1] for entry in entries])
    wanted_me = (me_name or "").strip().casefold()
    formats: dict[str, int] = {}
    system_senders: list[str] = []
    group_hint = False
    participants: list[str] = []
    seen: dict[tuple, int] = {}
    messages: list[ParsedMessage] = []
    for fmt, date, time, ampm, rest in entries:
        formats[fmt] = formats.get(fmt, 0) + 1
        sender, sep, body = rest.partition(": ")
        if not sep:
            group_hint = group_hint or bool(GROUP_EVENT.search(rest))
            continue
        sender = sender.translate(_BIDI).strip()
        classified = _classify(body)
        if classified is None:
            system_senders.append(sender)
            group_hint = group_hint or bool(GROUP_EVENT.search(body))
            continue
        msg_type, clean_body, has_media, edited = classified
        sent_at = _timestamp(date, time, ampm, order, tz)
        key = (sent_at, sender, clean_body or msg_type)
        seen[key] = seen.get(key, 0) + 1
        if sender not in participants:
            participants.append(sender)
        messages.append(ParsedMessage(
            wa_message_id=_message_id(sent_at, sender, clean_body or msg_type, seen[key]),
            sent_at=sent_at,
            sender=sender,
            body=clean_body,
            msg_type=msg_type,
            has_media=has_media,
            from_me=bool(wanted_me) and sender.casefold() == wanted_me,
            edited=edited,
            line_format=fmt,
        ))
    if not messages:
        raise ExportFormatError("no_messages_in_export")

    me = next((p for p in participants if wanted_me and p.casefold() == wanted_me), None)
    others = [p for p in participants if p != me]
    name = (
        chat_name_from_filename(filename)
        or (system_senders[0] if system_senders else None)
        or ", ".join(others[:3])
        or "WhatsApp chat"
    )
    return ParsedChat(
        name=name,
        chat_type="group" if group_hint or len(participants) > 2 else "contact",
        export_format=max(formats, key=formats.get),
        participants=participants,
        me_name=me,
        messages=messages,
    )


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def read_export(data: bytes, filename: str | None) -> tuple[str, str | None]:
    """Return (chat text, best filename for naming) from an uploaded .txt or .zip."""
    if not data.startswith(b"PK\x03\x04"):
        if len(data) > MAX_TEXT_BYTES:
            raise ExportFormatError("export_too_large")
        return _decode(data), filename
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ExportFormatError("invalid_zip") from exc
    with archive:
        texts = [
            info for info in archive.infolist()
            if info.filename.lower().endswith(".txt") and not info.filename.startswith("__MACOSX")
        ]
        if not texts:
            raise ExportFormatError("zip_has_no_chat_txt")
        chosen = next((i for i in texts if PurePosixPath(i.filename).name == "_chat.txt"), texts[0])
        if chosen.file_size > MAX_TEXT_BYTES:
            raise ExportFormatError("export_too_large")
        inner = PurePosixPath(chosen.filename).name
        name_source = inner if chat_name_from_filename(inner) else filename
        return _decode(archive.read(chosen)), name_source


def parse_export(
    data: bytes,
    filename: str | None,
    *,
    me_name: str | None = None,
    tz: timezone = DEFAULT_TZ,
) -> ParsedChat:
    text, name_source = read_export(data, filename)
    return parse_export_text(text, filename=name_source, me_name=me_name, tz=tz)
