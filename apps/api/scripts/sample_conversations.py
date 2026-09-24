"""WhatsApp sample conversations that continue the seed_drive datasets.

PO numbers, parts, revisions, and dates match the documents that
scripts/seed_drive.py uploads, so confirmed records and chats corroborate
each other:

    studionorth  Studio North Precision (precision engineering)
    food         Hoa Phuong Do Fresh Supply (food supply)

Rendered to real export files by scripts/generate_whatsapp_exports.py.
"""
from dataclasses import dataclass, field

IMAGE = {"media": "image"}
VOICE = {"media": "audio"}
DELETED = {"deleted": True}


def doc(name: str, pages: int) -> dict:
    return {"media": "document", "name": name, "pages": pages}


def edited(text: str) -> dict:
    return {"text": text, "edited": True}


@dataclass
class Conversation:
    name: str
    platform: str  # "ios" (zip with _chat.txt) or "android" (plain .txt)
    me: str
    messages: list[tuple[str, str, object]]  # (YYYY-MM-DD HH:MM, sender, text | marker dict)
    group_members: list[str] = field(default_factory=list)  # set for groups created by `me`


STUDIO_NORTH_ME = "Linh Tran"
FOOD_ME = "Phuong Nguyen"

STUDIO_NORTH = [
    Conversation(
        name="Jon Tan Meridian",
        platform="ios",
        me=STUDIO_NORTH_ME,
        messages=[
            ("2026-08-14 17:42", "Jon Tan Meridian", "Hi Linh, thanks for the Q3 review today. As discussed we'll consolidate SN-1001 into monthly releases from Oct"),
            ("2026-08-14 17:45", STUDIO_NORTH_ME, "Noted Jon. I'll send the revised release schedule by next week"),
            ("2026-08-14 17:46", "Jon Tan Meridian", "Also pls quote SN-1004 titanium bracket against Rev C drawing. Rev B is obsolete for new orders"),
            ("2026-08-14 17:47", STUDIO_NORTH_ME, "Ok. Can you share the Rev C drawing? We only have Rev B on file"),
            ("2026-08-17 09:03", "Jon Tan Meridian", doc("SN-1004-DWG Rev C.pdf", 3)),
            ("2026-08-17 09:03", "Jon Tan Meridian", "Main change is the mounting hole pattern, 4x M6 instead of M5"),
            ("2026-08-17 09:20", STUDIO_NORTH_ME, "Received. Quote by 28 Aug as agreed"),
            ("2026-08-27 16:11", STUDIO_NORTH_ME, "Hi Jon, quote for SN-1004 Rev C sent to your email. SGD 214.00/pc, MOQ 10, lead time 4 weeks (Ti bar is 21 days from Singmet)"),
            ("2026-08-27 16:30", "Jon Tan Meridian", "Thanks, will review with my boss"),
            ("2026-09-12 10:05", "Jon Tan Meridian", "PO MER-PO-4128 just sent by email. 3 lines: SN-1003, SN-1004, SN-1005"),
            ("2026-09-12 10:06", "Jon Tan Meridian", "SN-1004 must be Rev C ya"),
            ("2026-09-12 10:15", STUDIO_NORTH_ME, "Received, will acknowledge within 1 working day"),
            ("2026-09-14 08:52", "Jon Tan Meridian", "Linh sorry, change on MER-PO-4128 line 2\nSN-1004 qty from 43 to 60 pcs\nSame delivery date 3 Oct"),
            ("2026-09-14 08:53", "Jon Tan Meridian", "Revised PO Rev B coming this afternoon"),
            ("2026-09-14 09:10", STUDIO_NORTH_ME, "Noted. 60 pcs by 3 Oct is ok, we have enough Ti bar. Will ack against Rev B once received"),
            ("2026-09-14 14:37", "Jon Tan Meridian", doc("MER-PO-4128 Rev B.pdf", 2)),
            ("2026-09-14 14:52", STUDIO_NORTH_ME, edited("Acknowledged MER-PO-4128 Rev B. Line 2 SN-1004 Rev C x 60 pcs, delivery 3 Oct 2026")),
            ("2026-09-14 14:53", "Jon Tan Meridian", "👍"),
            ("2026-09-22 11:20", "Jon Tan Meridian", "Btw DO-7300 last month was 2 days late. Can make sure the anodizing slot is booked early for this one?"),
            ("2026-09-22 11:34", STUDIO_NORTH_ME, "Yes, booked Anodize-It for 28 Sep already. Will send you the CoC together with the DO"),
        ],
    ),
    Conversation(
        name="Aisha Semicon Dynamics",
        platform="android",
        me=STUDIO_NORTH_ME,
        messages=[
            ("2026-08-18 10:12", "Aisha Semicon Dynamics", "Hi Linh, can you pull in delivery for SEM-PO-4121? Our customer pushed the build earlier"),
            ("2026-08-18 10:13", "Aisha Semicon Dynamics", "Current date is 29 Aug, we need by 22 Aug if possible"),
            ("2026-08-18 11:40", STUDIO_NORTH_ME, "Checking with production. SN-1002 shafts are waiting for grinding, spindle under repair"),
            ("2026-08-18 15:05", STUDIO_NORTH_ME, "We can deliver 1 week early if we split the shipment:\n- SN-1003 manifold 37 pcs on 22 Aug\n- SN-1002 shaft 21 pcs on 29 Aug (grinding outsourced to Tuas Tooling)"),
            ("2026-08-18 15:21", "Aisha Semicon Dynamics", "Split shipment is fine. Send first batch when ready"),
            ("2026-08-21 17:02", STUDIO_NORTH_ME, "First batch ships tomorrow morning, DO will follow by email"),
            ("2026-08-22 09:48", "Aisha Semicon Dynamics", IMAGE),
            ("2026-08-22 09:48", "Aisha Semicon Dynamics", "Received 37 pcs, signed DO attached. Thanks!"),
            ("2026-08-26 12:30", "Aisha Semicon Dynamics", "Another PO coming this week, SEM-PO-4125. Steel base plates, aluminium housings and more shafts"),
            ("2026-08-26 12:31", "Aisha Semicon Dynamics", DELETED),
            ("2026-08-26 12:31", "Aisha Semicon Dynamics", "Need by 18 Sep"),
            ("2026-08-26 13:02", STUDIO_NORTH_ME, "Ok noted. 18 Sep should be fine, will confirm once PO received"),
            ("2026-08-28 16:44", "Aisha Semicon Dynamics", "Sent SEM-PO-4125 just now"),
            ("2026-08-29 09:15", STUDIO_NORTH_ME, "Acknowledged SEM-PO-4125: SN-1006 x25, SN-1001 x40, SN-1002 x55, delivery 18 Sep"),
        ],
    ),
    Conversation(
        name="SN x Harbour Marine",
        platform="ios",
        me=STUDIO_NORTH_ME,
        group_members=["Wei Jie Harbour Marine", "Kumar Harbour QA"],
        messages=[
            ("2026-09-07 09:30", STUDIO_NORTH_ME, "Hi all, creating this group for HAR-PO-4127 so QA and purchasing are in one place"),
            ("2026-09-07 09:41", "Wei Jie Harbour Marine", "Thanks Linh. PO sent this morning"),
            ("2026-09-08 14:05", "Kumar Harbour QA", "Please hold HAR-PO-4127. Rev A has the wrong qty for the SN-1003 manifold"),
            ("2026-09-08 14:06", "Kumar Harbour QA", IMAGE),
            ("2026-09-08 14:06", "Kumar Harbour QA", "Our drawing check found it, should be 42 not 30"),
            ("2026-09-08 14:20", STUDIO_NORTH_ME, "Held. Nothing cut yet. Which revision should we work to?"),
            ("2026-09-08 16:47", "Wei Jie Harbour Marine", "PO Rev B issued, qty 42 for SN-1003. SN-1002 shaft unchanged at 27"),
            ("2026-09-08 16:47", "Wei Jie Harbour Marine", doc("HAR-PO-4127 Rev B.pdf", 2)),
            ("2026-09-08 17:03", STUDIO_NORTH_ME, "Understood. We'll reissue the acknowledgement against PO Rev B. Drawing stays SN-1003 Rev A?"),
            ("2026-09-08 17:10", "Kumar Harbour QA", "Yes drawing Rev A is correct. Please include CMM report for first article"),
            ("2026-09-09 10:02", STUDIO_NORTH_ME, "Ack sent for HAR-PO-4127 Rev B. Delivery 28 Sep, CoC + CMM report with the DO"),
            ("2026-09-21 15:30", "Kumar Harbour QA", "Can we do FAI at your shop on 24 Sep instead of receiving inspection?"),
            ("2026-09-21 15:44", STUDIO_NORTH_ME, "Sure, 24 Sep 10am works. Priya from our QC will host"),
        ],
    ),
    Conversation(
        name="SN Production",
        platform="android",
        me=STUDIO_NORTH_ME,
        group_members=["Wei Ming", "Priya QC"],
        messages=[
            ("2026-08-31 08:15", STUDIO_NORTH_ME, "Morning. Week 36 priorities:\n1. SEM-PO-4121 second batch SN-1002 x21 (grinding at Tuas Tooling)\n2. HAR / MER Rev changes coming, pls don't start SN-1003 or SN-1004 yet"),
            ("2026-08-31 08:22", "Wei Ming", "Ok. Grinder spindle back Thursday, Tuas Tooling returns shafts Wed"),
            ("2026-08-31 08:40", "Priya QC", "MedFab FAI for SN-1005 bushing due 18 Sep, need CMM slot"),
            ("2026-08-31 08:41", STUDIO_NORTH_ME, "Priya can you own the MedFab FAI? Wei Ming to machine 5 samples by 11 Sep"),
            ("2026-08-31 08:45", "Wei Ming", "Can"),
            ("2026-09-08 17:20", STUDIO_NORTH_ME, "HAR-PO-4127 now Rev B, SN-1003 qty 42. Ok to start after ack tomorrow"),
            ("2026-09-11 16:58", "Wei Ming", IMAGE),
            ("2026-09-11 16:58", "Wei Ming", "5 SN-1005 samples done, passed to QC"),
            ("2026-09-14 09:15", STUDIO_NORTH_ME, "MER-PO-4128 line 2 SN-1004 increased to 60 pcs, Rev C drawing. Need Ti bar check"),
            ("2026-09-14 09:32", "Wei Ming", "Stock is 18kg, enough for 60 + scrap"),
            ("2026-09-17 18:05", "Priya QC", "SN-1005 FAI report done, all dims within tolerance. Submitting to MedFab tomorrow"),
        ],
    ),
]

FOOD = [
    Conversation(
        name="Chef Marcus Marina Table",
        platform="ios",
        me=FOOD_ME,
        messages=[
            ("2026-08-03 16:20", "Chef Marcus Marina Table", "Hi Phuong, order for tomorrow: 4 packs baby spinach"),
            ("2026-08-03 16:25", FOOD_ME, "Confirmed PO-5500. Delivery 7-9am slot as usual?"),
            ("2026-08-03 16:26", "Chef Marcus Marina Table", "Yes pls"),
            ("2026-08-12 17:48", "Chef Marcus Marina Table", "Tomorrow: 8 chicken breast 2kg and 11 sacks jasmine rice. Event on Saturday"),
            ("2026-08-12 17:55", FOOD_ME, "Noted, PO-5504. Halal cert will be with the DO"),
            ("2026-08-14 08:40", "Chef Marcus Marina Table", IMAGE),
            ("2026-08-14 08:41", "Chef Marcus Marina Table", "Last batch of tomatoes was soft, can check QC?"),
            ("2026-08-14 09:02", FOOD_ME, "Sorry chef. We'll photograph every crate before dispatch from now on. Credit for the tomatoes will be on next invoice"),
            ("2026-08-22 18:10", "Chef Marcus Marina Table", "For Mon: spinach 12, romaine 15, tiger prawns 18kg"),
            ("2026-08-22 18:12", "Chef Marcus Marina Table", edited("Sorry for Mon 24 Aug")),
            ("2026-08-22 18:20", FOOD_ME, "Confirmed PO-5508 for Mon 24 Aug, 7-9am"),
            ("2026-08-23 20:05", "Chef Marcus Marina Table", VOICE),
            ("2026-08-23 20:07", FOOD_ME, "Ok got it, prawns reduce to 15kg. Revised invoice tonight"),
        ],
    ),
    Conversation(
        name="Lyn Golden Wok",
        platform="android",
        me=FOOD_ME,
        messages=[
            ("2026-08-12 15:02", "Lyn Golden Wok", "Hi Phuong, our order for Fri: 9 sacks jasmine rice, 12 tins cooking oil, 15 cherry tomatoes"),
            ("2026-08-12 15:10", FOOD_ME, "Noted, will issue PO-5505 for delivery 14 Aug"),
            ("2026-08-13 11:31", "Lyn Golden Wok", "Can we change PO-5505 rice from 9 to 12 sacks? Wedding job came in"),
            ("2026-08-13 11:45", FOOD_ME, "Done, updated to 12 sacks"),
            ("2026-08-13 11:46", "Lyn Golden Wok", "And oil reduce to 8 tins, we still have stock"),
            ("2026-08-13 11:52", FOOD_ME, "Ok PO-5505 revised:\nRice 12 sacks\nOil 8 tins\nCherry tomatoes 15\nNew total on the revised invoice"),
            ("2026-08-14 10:15", "Lyn Golden Wok", IMAGE),
            ("2026-08-14 10:15", "Lyn Golden Wok", "Tomatoes bruised again, 3 packs"),
            ("2026-08-14 10:30", FOOD_ME, "So sorry Lyn. Will credit 3 packs and QC (Mei) will photograph crates before dispatch"),
        ],
    ),
    Conversation(
        name="Anh Little Saigon",
        platform="android",
        me=FOOD_ME,
        messages=[
            ("2026-08-18 13:15", "Anh Little Saigon", "Hi, PO-5507 for tomorrow: 11 cherry tomatoes and 14 baby spinach"),
            ("2026-08-18 13:20", FOOD_ME, "Confirmed, Wed 19 Aug 8am"),
            ("2026-08-18 19:42", "Anh Little Saigon", "Sorry pls hold tomorrow's delivery, kitchen renovation running late"),
            ("2026-08-18 19:50", FOOD_ME, "Held. Reschedule to Thursday same items?"),
            ("2026-08-18 20:01", "Anh Little Saigon", "Thursday ok but drop the spinach, we overstocked"),
            ("2026-08-18 20:05", FOOD_ME, "PO-5507 revised: spinach removed, cherry tomatoes 11, delivery Thu 20 Aug 8am. Daniel will deliver"),
            ("2026-08-20 08:22", "Anh Little Saigon", "Received thanks"),
        ],
    ),
    Conversation(
        name="Azure Sky F&B Orders",
        platform="ios",
        me=FOOD_ME,
        group_members=["Chef Hendra Azure Sky", "Grace Azure Sky Purchasing"],
        messages=[
            ("2026-08-07 10:00", FOOD_ME, "Hi Chef Hendra, Grace. Group for Azure Sky orders so changes are in one place"),
            ("2026-08-07 10:12", "Grace Azure Sky Purchasing", "Thanks. PO-5502 for Sun: prawns 6kg, barramundi 9 fillets, chicken breast 12"),
            ("2026-08-07 10:30", "Chef Hendra Azure Sky", "Barramundi pls portion 180g not 200g. Plating change"),
            ("2026-08-07 10:41", FOOD_ME, "Our standard is 200g. 180g possible from next week, I'll send updated spec sheet"),
            ("2026-08-07 10:43", "Chef Hendra Azure Sky", "Ok this week 200g fine"),
            ("2026-08-20 11:55", "Grace Azure Sky Purchasing", "Reminder: standing order changes by Wed noon, 20% flex as agreed in contract review"),
            ("2026-08-20 12:05", "Grace Azure Sky Purchasing", doc("Azure Sky Standing Order Sep.pdf", 1)),
            ("2026-08-20 12:20", FOOD_ME, "Received. Seafood price fixed through December as agreed"),
            ("2026-08-26 11:48", "Chef Hendra Azure Sky", "This week +20% prawns, big corporate lunch Friday"),
            ("2026-08-26 11:58", FOOD_ME, "Noted, within flex. Will add to Friday delivery"),
        ],
    ),
]

DATASETS = {"studionorth": STUDIO_NORTH, "food": FOOD}
