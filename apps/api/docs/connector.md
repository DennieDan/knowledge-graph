# The assistant connector (MCP)

Ticket #94 (F-03, "Answers from the record, anywhere"). Owners already use
ChatGPT or Claude, so crosspod's record is readable from inside them over the
Model Context Protocol. The connector is read-only: an assistant can find
records, open them with their sources, and see their history. It cannot change
anything.

## The three tools

| Tool | What it does |
|---|---|
| `search` | Find orders and other records by PO number, customer, item or plain words. Up to 10 results, confirmed first. Each title says who checked the record. |
| `fetch` | Open one record: its lines marked with their sources (`[S1]`), the fields confirmed one by one in the review queue, and the quoted passage from each source. |
| `history` | What happened to one record, oldest first: revisions, who confirmed it and how (one record, a batch, or automatically), edits, replies and re-checks. |

`search` and `fetch` keep the shapes ChatGPT requires of connectors, so the same
server works in ChatGPT chat and deep research. Every tool is annotated
read-only and returns typed JSON (an output schema), so provenance travels as
data rather than prose.

## Keys

Each assistant gets its own key (`ck_…`). A key reads with the walls of the
person who created it: their company, shared records plus their own private
ones, and only the sources they may open. Keys are stored as SHA-256 hashes,
shown once, listed in settings and switched off in one call.

- Settings API: `GET / POST /accounts/{id}/connector-keys`,
  `DELETE /accounts/{id}/connector-keys/{key_id}`. Owners and admins see and
  switch off every key in the company; others see their own.
- Locally: `python -m scripts.connector_key create --email you@example.com --name "Claude Desktop"`.
- Planner and supervisor cannot create keys yet: their field rules hide prices,
  and a record's prose can mention a price outside a price field. They get keys
  once field rules reach the prose (#101).

## Connecting an assistant

Use the API's own public URL (`PUBLIC_API_URL`, the Render `kg-api` address),
not the web app's `/backend` proxy. Below, `https://api.example` stands for it.

**Claude Code**

```
claude mcp add --transport http crosspod https://api.example/mcp --header "Authorization: Bearer ck_…"
```

**Claude (claude.ai, Claude Desktop)**: Settings → Connectors → Add custom
connector, URL `https://api.example/mcp/k/ck_…`. The key sits in the URL because
the custom-connector form offers OAuth or no authentication, with no header
field.

**Claude Desktop against a local database** (development): stdio, in
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "crosspod": {
      "command": "/bin/sh",
      "args": ["-c", "cd /path/to/knowledge-graph/apps/api && .venv/bin/python -m scripts.connector_stdio"],
      "env": { "CONNECTOR_KEY": "ck_…" }
    }
  }
}
```

**ChatGPT** (Plus, Pro, Business, Enterprise, Edu): Settings → Apps &
Connectors → Advanced → turn on Developer mode, then Create. Name `crosspod`,
URL `https://api.example/mcp/k/ck_…`, authentication "No authentication" (the
key is in the URL).

**OpenAI API** (Responses):

```json
{ "type": "mcp", "server_label": "crosspod", "server_url": "https://api.example/mcp",
  "headers": { "Authorization": "Bearer ck_…" }, "require_approval": "never" }
```

## What keeps it read-only and walled

1. Tool annotations say read-only. Hosts use them to skip approval prompts; the
   protocol tells clients not to trust them, so they are not the boundary.
2. The tools only call read functions (`app/connector.py`).
3. Each call runs in a `READ ONLY` Postgres transaction with the RLS
   organization set (`set_request_org`). Not even a bug can write.

Walls, per call: the key's company only; records private to someone else are
never found; a line read only from a chat the key holder cannot see is withheld
and counted; field rules follow the holder's current role; a holder removed from
the company, or moved to a price-hidden role, is cut off at once.

Records and passages are customer text, so a document can try to instruct the
assistant. The server instructions and payloads mark that text as data.

## Known limits and follow-ups

- **OAuth.** Keys in URLs are redacted from the API's access log, but a host or
  proxy in front of it may still log the path. Prefer the header form where the
  assistant supports it, and switch off any key that may have leaked. The
  protocol's own OAuth flow (ChatGPT recommends Client ID Metadata Documents)
  replaces URL keys next.
- **Settings screen.** The key API is in place; the web settings card is not.
- **Approving from the assistant** is feature 13 (#104), out of scope here.
