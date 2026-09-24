MEETING_PROMPT = (
    "Extract one business meeting (meeting notes, minutes, or a call summary) "
    "and write a concise natural-language report for an operations user.\n"
    "Set report to 2–4 short paragraphs, each represented as one EvidenceValue. "
    "Write complete sentences rather than labels or bullet points. "
    "Begin with what the meeting was about, when it took place, and who attended, "
    "then summarize the decisions made, action items with their owners and due dates, and open follow-ups. "
    "Mention only useful supported facts, omit missing details, "
    "and state material uncertainty or conflicting evidence plainly. "
    "Each paragraph must cite every evidence chunk needed to support its sentences.\n"
    "Also populate the structured title, date, attendee, decision, action item, follow-up, and reference fields. "
    "Reference the orders, clients, items, suppliers, and supplier orders the meeting discussed. "
    "Keep dates exactly as stated. "
    "Do not repeat the report as a field-by-field list."
)

MEETING_QUERIES = (
    "meeting notes minutes agenda date attendees",
    "meeting decisions agreed approved",
    "meeting action items owner due date follow up",
)
