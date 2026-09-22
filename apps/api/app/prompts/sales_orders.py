SALES_ORDER_PROMPT = """Extract one customer sales order. Do not treat supplier orders, quotations, invoices, delivery orders, or production jobs as sales orders.
Capture order/customer identity, dates, line items, terms, delivery requirements, changes, approvals, references, conflicts, and open questions.
Keep quantities and units exactly as stated. Do not resolve conflicting revisions silently."""

SALES_ORDER_QUERIES = (
    "customer sales order number customer identity",
    "sales order date requested delivery date delivery instructions",
    "sales order line items item codes descriptions quantities units prices",
    "sales order payment terms currency",
    "sales order revisions changes approvals conflicts",
)
