CLIENT_PROMPT = """Extract one client/customer record. Capture identity, contacts, addresses, terms, and references.
A name alone is not a registration number or durable customer ID. Report competing identities or terms as conflicts."""

CLIENT_QUERIES = (
    "client legal name registration number customer account identifier",
    "client contacts billing address delivery address",
    "client payment terms delivery terms",
    "sales orders and item codes associated with this client",
)
