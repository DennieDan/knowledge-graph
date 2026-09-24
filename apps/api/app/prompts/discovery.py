DISCOVERY_PROMPT = """Identify mentions of only these business entities: customer sales orders, clients/customers, sold items/products, suppliers/vendors, supplier orders, and meetings.
A sales order is an order received from a customer, not a supplier purchase, quotation, invoice, delivery order, or production job.
A supplier is a company this business buys materials or services from, including subcontractors; a customer is never a supplier.
A supplier order is a purchase order this business placed with a supplier or subcontractor, not a customer sales order, quotation, or invoice.
A meeting is a specific meeting, call, or discussion recorded in meeting notes or minutes; name it by its title or subject.
For each candidate, return its displayed name, all explicit identifiers, and citations. Use identifier keys such as order_number, customer_identifier, registration_number, customer_id, internal_sku, customer_item_code, client_identifier, supplier_id, purchase_order_number, and meeting_date.
Use purchase_order_number only for supplier orders and order_number only for sales orders. Set meeting_date to the meeting date as YYYY-MM-DD when it is stated.
Do not combine separate entities. Do not emit Files or Conversations as candidates."""
