CLIENT_PROMPT = (
    "Extract one client/customer record and write a concise natural-language report for an operations user.\n"
    "Set report to 2–3 short paragraphs, each represented as one EvidenceValue. "
    "Write complete sentences rather than labels or bullet points. "
    "Begin with who the client is, then summarize available contacts, locations, commercial terms, "
    "and relevant order or item relationships. "
    "Mention only useful supported facts, omit missing details, "
    "and state material uncertainty or conflicting evidence plainly. "
    "Each paragraph must cite every evidence chunk needed to support its sentences.\n"
    "Also populate the structured identity, contact, address, term, and reference fields. "
    "A name alone is not a registration number or durable customer ID. "
    "Do not repeat the report as a field-by-field list."
)

CLIENT_QUERIES = (
    "client legal name registration number customer account identifier",
    "client contacts billing address delivery address",
    "client payment terms delivery terms",
    "sales orders and item codes associated with this client",
)
