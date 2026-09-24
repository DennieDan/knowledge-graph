"""Render sample conversations as WhatsApp "Export chat → Without media" files.

Run from apps/api with the virtual environment active:

    python -m scripts.generate_whatsapp_exports            # -> fixtures/whatsapp/
    python -m scripts.generate_whatsapp_exports --out /tmp/wa

Output mirrors what the phones produce (English, Singapore region, 12-hour):

    iOS      WhatsApp Chat - <name>.zip  containing  _chat.txt
             [14/8/26, 5:42:07 PM] Jon Tan Meridian: text
    Android  WhatsApp Chat with <name>.txt
             14/08/2026, 5:42 pm - Aisha Semicon Dynamics: text

including the U+200E marks iOS puts before system/media lines, the U+202F
narrow space before AM/PM, the end-to-end encryption notice, group-creation
lines, media/document placeholders, deleted and edited markers, and
multi-line messages. Content lives in scripts/sample_conversations.py.
"""
import argparse
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.sample_conversations import DATASETS, Conversation  # noqa: E402

LRM = "\u200e"
NNBSP = "\u202f"
E2E = "Messages and calls are end-to-end encrypted. Only people in this chat can read, listen to, or share them."
OUT_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "whatsapp"
ZIP_TIME = (2026, 9, 24, 12, 0, 0)


def _clock(when: datetime) -> tuple[int, str]:
    return (when.hour % 12 or 12), ("AM" if when.hour < 12 else "PM")


def ios_stamp(when: datetime) -> str:
    hour, meridiem = _clock(when)
    return f"[{when.day}/{when.month}/{when:%y}, {hour}:{when:%M:%S}{NNBSP}{meridiem}]"


def android_stamp(when: datetime) -> str:
    hour, meridiem = _clock(when)
    return f"{when:%d/%m/%Y}, {hour}:{when:%M}{NNBSP}{meridiem.lower()} -"


def _timeline(conversation: Conversation) -> list[tuple[datetime, str, object]]:
    """Attach deterministic, strictly increasing seconds within each minute."""
    per_minute: dict[str, int] = {}
    timeline = []
    for index, (minute, sender, content) in enumerate(conversation.messages):
        count = per_minute.get(minute, 0)
        per_minute[minute] = count + 1
        second = min(59, 4 + count * 11 + index % 5)
        timeline.append((datetime.fromisoformat(minute).replace(second=second), sender, content))
    return timeline


def render_ios(conversation: Conversation) -> str:
    timeline = _timeline(conversation)
    start = timeline[0][0] - timedelta(minutes=3)
    lines = [f"{ios_stamp(start)} {conversation.name}: {LRM}{E2E}"]
    if conversation.group_members:
        lines.append(f"{LRM}{ios_stamp(start)} {conversation.name}: {LRM}You created group “{conversation.name}”")
        for member in conversation.group_members:
            lines.append(f"{LRM}{ios_stamp(start + timedelta(seconds=20))} {conversation.name}: {LRM}You added {member}")
    for when, sender, content in timeline:
        stamp = ios_stamp(when)
        if isinstance(content, str):
            lines.append(f"{stamp} {sender}: {content}")
        elif content.get("deleted"):
            text = "You deleted this message." if sender == conversation.me else "This message was deleted."
            lines.append(f"{LRM}{stamp} {sender}: {LRM}{text}")
        elif content.get("edited"):
            lines.append(f"{stamp} {sender}: {content['text']} {LRM}<This message was edited>")
        elif content["media"] == "document":
            pages = content["pages"]
            label = f"{pages} page" if pages == 1 else f"{pages} pages"
            lines.append(f"{LRM}{stamp} {sender}: {content['name']} • {LRM}{label} {LRM}document omitted")
        else:
            lines.append(f"{LRM}{stamp} {sender}: {LRM}{content['media']} omitted")
    return "\n".join(lines)


def render_android(conversation: Conversation) -> str:
    timeline = _timeline(conversation)
    start = timeline[0][0] - timedelta(minutes=3)
    lines = [f"{android_stamp(start)} {E2E} Learn more."]
    if conversation.group_members:
        lines.append(f"{android_stamp(start)} You created group \"{conversation.name}\"")
        lines.append(f"{android_stamp(start)} You added {' and '.join(conversation.group_members)}")
    for when, sender, content in timeline:
        prefix = f"{android_stamp(when)} {sender}:"
        if isinstance(content, str):
            lines.append(f"{prefix} {content}")
        elif content.get("deleted"):
            lines.append(f"{prefix} {'You deleted this message' if sender == conversation.me else 'This message was deleted'}")
        elif content.get("edited"):
            lines.append(f"{prefix} {content['text']} <This message was edited>")
        else:
            lines.append(f"{prefix} <Media omitted>")
    return "\n".join(lines) + "\n"


def write_conversation(conversation: Conversation, folder: Path) -> Path:
    if conversation.platform == "android":
        path = folder / f"WhatsApp Chat with {conversation.name}.txt"
        path.write_text(render_android(conversation), encoding="utf-8")
        return path
    path = folder / f"WhatsApp Chat - {conversation.name}.zip"
    info = zipfile.ZipInfo("_chat.txt", date_time=ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(info, render_ios(conversation).encode("utf-8"))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--dataset", choices=sorted(DATASETS), action="append")
    arguments = parser.parse_args()
    for name in arguments.dataset or sorted(DATASETS):
        folder = arguments.out / name
        folder.mkdir(parents=True, exist_ok=True)
        for conversation in DATASETS[name]:
            path = write_conversation(conversation, folder)
            print(f"{name}: {path.name} ({len(conversation.messages)} messages, me = {conversation.me})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
