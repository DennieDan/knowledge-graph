ITEM_PROMPT = """Extract one sold item/product record. Capture identity, aliases, technical attributes, revisions, commercial details, and references.
Distinguish an internal SKU from a customer-specific item code. A description alone is not a stable identifier."""

ITEM_QUERIES = (
    "item internal SKU customer item code product identity aliases",
    "item description material dimensions tolerances unit",
    "item drawing specification revision",
    "item packaging lead time client and sales order references",
)
