SALES_ORDER_PROMPT = """Extract one customer sales order and write a concise natural-language report for an operations user. Do not treat supplier orders, quotations, invoices, delivery orders, or production jobs as sales orders.
Set report to 2–4 short paragraphs, each represented as one EvidenceValue. Write complete sentences rather than labels or bullet points. Summarize the customer and order identity, what was ordered and in what quantities, important dates and delivery requirements, commercial terms, and any later changes or approvals. Lead with the current operational picture. Mention only useful supported facts, omit missing details, and state material uncertainty, revision conflicts, or required follow-up plainly. Each paragraph must cite every evidence chunk needed to support its sentences.
Also populate the structured order, line-item, term, delivery, change, reference, conflict, and open-question fields. Keep quantities and units exactly as stated. Do not resolve conflicting revisions silently or repeat the report as a field-by-field list."""

SALES_ORDER_QUERIES = (
    "customer sales order number customer identity",
    "sales order date requested delivery date delivery instructions",
    "sales order line items item codes descriptions quantities units prices",
    "sales order payment terms currency",
    "sales order revisions changes approvals conflicts",
)
