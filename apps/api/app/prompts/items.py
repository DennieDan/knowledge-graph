ITEM_PROMPT = (
    "Extract one sold item/product record and write a concise natural-language report for an operations user.\n"
    "Set report to 2–3 short paragraphs, each represented as one EvidenceValue. "
    "Write complete sentences rather than labels or bullet points. "
    "Begin with what the item is and how it is identified, then summarize supported technical requirements, "
    "revision information, packaging, lead-time, commercial context, and client or order relationships. "
    "Mention only useful supported facts, omit missing details, "
    "and state material uncertainty or conflicting specifications plainly. "
    "Each paragraph must cite every evidence chunk needed to support its sentences.\n"
    "Also populate the structured identity, technical, commercial, and reference fields. "
    "Distinguish an internal SKU from a customer-specific item code. "
    "A description alone is not a stable identifier. "
    "Do not repeat the report as a field-by-field list."
)

ITEM_QUERIES = (
    "item internal SKU customer item code product identity aliases",
    "item description material dimensions tolerances unit",
    "item drawing specification revision",
    "item packaging lead time client and sales order references",
)
