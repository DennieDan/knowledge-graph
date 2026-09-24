SUPPLIER_PROMPT = (
    "Extract one supplier/vendor record (a company this business buys materials or services from, "
    "including subcontractors) and write a concise natural-language report for an operations user. "
    "Do not treat customers/clients as suppliers.\n"
    "Set report to 2–3 short paragraphs, each represented as one EvidenceValue. "
    "Write complete sentences rather than labels or bullet points. "
    "Begin with who the supplier is and what it supplies, then summarize available contacts, locations, "
    "prices, lead times, commercial terms, delivery performance, and relevant supplier order or item relationships. "
    "Mention only useful supported facts, omit missing details, "
    "and state material uncertainty or conflicting evidence plainly. "
    "Each paragraph must cite every evidence chunk needed to support its sentences.\n"
    "Also populate the structured identity, contact, address, supplied item, price, lead-time, term, "
    "performance, and reference fields. "
    "A name alone is not a registration number or durable supplier ID. "
    "Do not repeat the report as a field-by-field list."
)

SUPPLIER_QUERIES = (
    "supplier vendor legal name registration number supplier code",
    "supplier contacts address",
    "supplier materials services supplied prices quotation lead time",
    "supplier payment terms delivery terms performance late delivery quality issue",
    "purchase orders and items associated with this supplier",
)
