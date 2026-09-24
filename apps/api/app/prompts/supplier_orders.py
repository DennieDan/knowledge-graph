SUPPLIER_ORDER_PROMPT = (
    "Extract one supplier order (a purchase order this business placed with a supplier or subcontractor) "
    "and write a concise natural-language report for an operations user. "
    "Do not treat customer sales orders, quotations, invoices, delivery orders, or production jobs as supplier orders.\n"
    "Set report to 2–4 short paragraphs, each represented as one EvidenceValue. "
    "Write complete sentences rather than labels or bullet points. "
    "Summarize the supplier and purchase order identity, what was ordered and in what quantities, "
    "prices, expected delivery dates and location, commercial terms, and any later changes, delays, or approvals. "
    "Lead with the current operational picture. "
    "Mention only useful supported facts, omit missing details, and state material uncertainty, "
    "revision conflicts, or required follow-up plainly. "
    "Each paragraph must cite every evidence chunk needed to support its sentences.\n"
    "Also populate the structured order, line-item, term, delivery, change, and reference fields. "
    "Keep quantities and units exactly as stated. "
    "Do not resolve conflicting revisions silently or repeat the report as a field-by-field list."
)

SUPPLIER_ORDER_QUERIES = (
    "purchase order number supplier identity",
    "purchase order date expected delivery date delivery location",
    "purchase order line items item codes descriptions quantities units prices",
    "purchase order payment terms currency",
    "purchase order revisions changes delays approvals",
)
