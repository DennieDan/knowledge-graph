DISCOVERY_PROMPT = """Identify mentions of only these business entities: customer sales orders, clients/customers, and sold items/products.
A sales order is an order received from a customer, not a supplier purchase, quotation, invoice, delivery order, or production job.
For each candidate, return its displayed name, all explicit identifiers, and citations. Use identifier keys such as order_number, customer_identifier, registration_number, customer_id, internal_sku, customer_item_code, and client_identifier.
Do not combine separate entities. Do not emit Files or Conversations as candidates."""
