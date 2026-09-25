# WhatsApp integration via WAHA

The API imports WhatsApp chat history through a self-hosted
[WAHA](https://waha.devlike.pro/) (WhatsApp HTTP API) container. This document
covers why WAHA was chosen, how it fits into this project, how to run it, and
how to test the integration.

## Why WAHA

WAHA is an open-source HTTP wrapper around the WhatsApp Web protocol. We run it
as a Docker sidecar; the FastAPI backend talks to it over REST and never speaks
the WhatsApp protocol directly.

Reasons for choosing it:

- **Chat history access.** WAHA exposes `GET /chats` and paginated
  `GET /chats/{id}/messages`, which lets a user pick chats and backfill their
  history. The official Meta Cloud API cannot import existing chat history at
  all — it only delivers new messages to a business number.
- **Self-hosted.** The session store and all message traffic stay on our own
  infrastructure. No third party sees message content.
- **Familiar auth UX.** Linking works exactly like WhatsApp Web: scan a QR code
  or enter a pairing code. No Meta app review, business verification, or
  per-message pricing.
- **Per-user sessions.** Each app user gets an isolated WAHA session, so one
  deployment can serve many linked accounts.
- **Webhooks.** Optional push delivery of new messages and session status
  changes for incremental sync.

### Risk: development-only

WAHA uses the **unofficial** WhatsApp Web protocol. Using it violates WhatsApp's
Terms of Service, and linked numbers can be banned without warning. For that
reason:

- WAHA is accepted **for development and testing only**, on a spare personal
  number where a ban is acceptable.
- It must **not** be connected to a customer number without a new, explicit
  production decision.
- The production ingestion path remains **export-file first**, with the
  official Meta Cloud API (Coexistence) as a possible later option.

## How it is used

```text
web (whatsapp-connect modal)
        |  /whatsapp/* REST, session cookie auth
        v
api (FastAPI)  ──httpx──>  WAHA container (127.0.0.1:3100)
        |                       |
        v                       v
   PostgreSQL            .sessions volume
   whatsapp_* tables     (WhatsApp credentials)
```

- `apps/api/waha/docker-compose.yml` — the WAHA service (GOWS engine), bound to
  `127.0.0.1:3100`, API-key protected, sessions persisted in a named volume.
- `apps/api/app/waha_client.py` — thin httpx client: create/start/delete
  sessions, QR and pairing-code auth, chat overview, paginated messages.
- `apps/api/app/whatsapp.py` — the `/whatsapp/*` router (endpoints below).
- `apps/web/app/components/whatsapp-connect.tsx` — the connect → pick chats →
  import modal.

### Session model

One WAHA session per app user. The session name is derived from the user id
(`u_<user_id_hex>`), so connect is idempotent — calling it twice just restarts
the existing session. Session status (`STARTING` → `SCAN_QR_CODE` → `WORKING`,
or `FAILED`/`STOPPED`) is synced from WAHA on every status read, and pushed via
webhook when configured.

### Storage

Three user-scoped tables (migration `0003_whatsapp`):

| Table | Purpose |
| --- | --- |
| `whatsapp_connections` | One row per user: WAHA session name, linked phone number, status. |
| `whatsapp_chats` | Chats discovered for a connection; `import_status` is `none`/`importing`/`imported`/`failed`. |
| `whatsapp_messages` | Imported messages. Unique `(chat_id, wa_message_id)` makes imports idempotent; `raw` JSONB keeps the original payload. |

These tables deliberately have **no `organization_id`** — imported chats belong
to the person, never to a workspace. Disconnecting (`DELETE /whatsapp/connect`)
cascades and deletes the chats and messages.

**Claim seam (#93 Step 2).** When a fact is proposed from a WhatsApp message into
an org record, the claim still has two owners: `organization_id` (who owns the
record) and `visible_via_user_id` (the connection's user — who was allowed to
see the source). Use `app.claims.create_claim`, which requires
`visible_via_user_id` for WhatsApp origins. Feature 10's permission check must
honour both, or a private chat leaks to the company through a confirmed record.

### Endpoints

All require the session cookie except `/whatsapp/webhooks`.

| Method & path | Description |
| --- | --- |
| `POST /whatsapp/connect` | Create/start the user's WAHA session. Returns `{status, phone_number}`. |
| `GET /whatsapp/connect/status` | Sync and return session status. |
| `GET /whatsapp/connect/qr` | Current QR code as `{mimetype, data(base64)}`. |
| `POST /whatsapp/connect/pairing` | Body `{phone_number}` → `{code}` to type into WhatsApp. |
| `DELETE /whatsapp/connect` | Delete the WAHA session and all imported data. |
| `GET /whatsapp/chats` | Fetch chat overview from WAHA, upsert rows, return the list. |
| `POST /whatsapp/imports` | Body `{chat_ids: [...]}` → queues a background history import. |
| `GET /whatsapp/imports` | Per-chat import status, error, and message count. |
| `POST /whatsapp/webhooks` | WAHA event sink (`message`, `session.status`); authenticated by `X-Webhook-Token`. |

Imports run as a FastAPI background task that pages through
`get_messages` (100/page) and upserts each message. Webhooks only store
messages for chats whose `import_status` is `imported`, so incremental sync
applies to chats the user explicitly imported. If `WAHA_WEBHOOK_URL` is unset,
new sessions get no webhook and the system runs in poll-only mode — fine for
the MVP.

## Chat export upload (no linking)

The WhatsApp modal opens on a choice: **Upload chat export** or **Link
WhatsApp**. Uploads need no WAHA and are the path for demo/test accounts.

- `app/whatsapp_export.py` parses iOS (`WhatsApp Chat - <name>.zip` →
  `_chat.txt`, `[d/m/yy, h:mm:ss AM] Name: …`) and Android
  (`WhatsApp Chat with <name>.txt`, `dd/mm/yyyy, h:mm am - Name: …`) exports:
  any date order, 12/24-hour clocks, U+200E/U+202F marks, multi-line
  messages, system lines (skipped), media/document placeholders, deleted and
  edited markers. Times are device-local; Singapore (UTC+8) is assumed.
- Uploaded chats reuse `whatsapp_chats` / `whatsapp_messages` with
  `origin='export'`, so transcripts, Conversations records and search work
  unchanged. `chat_jid` is `export_<hash(user, chat name)>@export` and message
  ids hash `(time, sender, body, ordinal)`: re-uploading a longer export of the
  same chat only adds new messages.
- The uploader's own messages are matched by the "Your name in these chats"
  field (defaults to the account display name).
- Uploads never mark WhatsApp as linked; the Sources card shows
  "Chats uploaded · no live sync". **Wipe out imported chats** deletes the
  uploaded chats, their transcript documents, and their Conversations
  records. **Disconnect** (WAHA) keeps uploaded chats.

| Method & path | Description |
| --- | --- |
| `POST /whatsapp/uploads` | Multipart `file` (.txt/.zip, ≤ 5 MB), `organization_id`, optional `me_name`. Parses, stores, and ingests synchronously. |
| `GET /whatsapp/uploads` | Uploaded chats for the current user. |
| `DELETE /whatsapp/uploads` | Wipe out all uploaded chats and their derived records. |

### Sample exports

`python -m scripts.generate_whatsapp_exports` writes
`fixtures/whatsapp/{studionorth,food}/` from
`scripts/sample_conversations.py`. The chats continue the `seed_drive`
datasets (same POs, parts, revisions, dates); the "me" names are `Linh Tran`
(Studio North) and `Phuong Nguyen` (food supply) — type these in the upload
dialog so those messages render as "Me".

## Setup

### Local development

Prerequisites: Docker, and a **spare** WhatsApp number you can afford to lose.

1. Start WAHA. On Apple Silicon use the `-arm` image tag; on x86 omit it
   (defaults to `gows`):

   ```sh
   WAHA_IMAGE_TAG=gows-arm WAHA_API_KEY=dev-secret WAHA_DASHBOARD_PASSWORD=devpass \
     docker compose -f apps/api/waha/docker-compose.yml up -d
   ```

2. Verify it is up:

   ```sh
   curl -H "X-Api-Key: dev-secret" http://localhost:3100/api/sessions
   # -> []
   ```

   The dashboard is at `http://localhost:3100/dashboard` (admin / devpass).

3. Add to `apps/api/.env`:

   ```env
   WAHA_BASE_URL=http://localhost:3100
   WAHA_API_KEY=dev-secret
   # Optional — enables live incremental sync. host.docker.internal lets the
   # container reach the API on the host. Omit for poll-only mode.
   WAHA_WEBHOOK_URL=http://host.docker.internal:8000/whatsapp/webhooks
   WAHA_WEBHOOK_SECRET=<openssl rand -hex 32>
   ```

   Note: `WAHA_WEBHOOK_URL` is only registered on sessions created **after** it
   is set — reconnect (DELETE + POST `/whatsapp/connect`) if you add it later.

4. Run migrations and start the apps:

   ```sh
   cd apps/api && python -m alembic upgrade head && cd ../..
   pnpm dev
   ```

5. In the web app, open the WhatsApp section, click **Connect**, then scan the
   QR code (WhatsApp → Settings → Linked devices → Link a device) or request a
   pairing code. Pick chats and import.

### Production notes (if ever approved)

- Always-on Docker host; x86 hosts use the default `devlikeapro/waha:gows`
  image.
- Keep the `waha_sessions` volume (or switch to PostgreSQL session storage) so
  restarts don't force re-scanning. `WHATSAPP_RESTART_ALL_SESSIONS` is already
  enabled.
- Put WAHA behind a TLS reverse proxy with DNS; keep the port off the public
  interface.
- Strong `WAHA_API_KEY` and dashboard password; disable the dashboard/Swagger
  or restrict them at the proxy — the dashboard controls every linked account.
- `WAHA_WEBHOOK_URL` must be the API's public URL.
- Choose the hosting region deliberately — Singapore is suggested while the
  PDPA/data-residency question (issue #29) is open.

## Testing

### Automated

`apps/api/tests/test_whatsapp.py` mocks `waha_client`, so no WAHA container is
needed. From `apps/api` with the venv active and a migrated database:

```sh
python -m unittest discover -s tests -v   # or: pnpm --filter api test
python -m alembic check                   # models match migrations
```

Coverage: connect idempotency, status sync, chat upserts, idempotent import,
webhook token auth, session-status updates, message storage, ignore rules for
non-imported chats, and 401s without auth.

### Manual end-to-end

1. WAHA running and reachable (`curl ... /api/sessions` returns `[]`).
2. Sign in to the web app, open WhatsApp → **Connect**.
3. Scan the QR code (or use pairing code) with the **spare** phone. Status
   should reach `WORKING` and show the phone number.
4. The chat list should populate. Select one small chat, click **Import**, and
   watch the status change `importing` → `imported` with a message count.
5. Re-run the import — the count should not grow (dedup via `wa_message_id`).
6. If webhooks are configured, send a message to the linked number from another
   phone; `GET /whatsapp/imports` should show `message_count` increment and
   `GET /whatsapp/chats` should show a newer `last_message_at`.
7. **Disconnect** when done — it deletes the WAHA session and all imported rows.

Useful checks while testing:

```sh
# WAHA-side session state
curl -H "X-Api-Key: dev-secret" http://localhost:3100/api/sessions

# Simulate a webhook event
curl -X POST http://localhost:8000/whatsapp/webhooks \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: $WAHA_WEBHOOK_SECRET" \
  -d '{"event":"session.status","session":"u_<user_id_hex>","payload":{"status":"WORKING"}}'
```
