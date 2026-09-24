---
name: testing-knowledge-graph
description: Local e2e setup for DennieDan/knowledge-graph — DB fallback when Docker Hub is rate-limited, OAuth-free session forging, seeding chat/stack rows, and capturing transient pending UI states.
---

# Testing knowledge-graph locally end-to-end

## Devin Secrets Needed
- `SESSION_SECRET` — you generate it locally (`openssl rand -hex 32` into `apps/api/.env`); no external secret needed.
- `OPENAI_API_KEY` — usually absent. Without it, `POST /accounts/{org}/chat/threads/{id}/messages` returns HTTP 500 (LLM client raises), so the UI shows "Could not get an answer. Try again." rather than a real answer. Seed `chat_messages` rows directly to exercise the answered/not-answered render paths.

## Database when Docker Hub is rate-limited
`docker compose up -d --wait db` can fail with `429 Too Many Requests` pulling `pgvector/pgvector`. Fallback that works:
1. `sudo -n apt-get update && sudo -n apt-get install -y postgresql-14 postgresql-server-dev-14`
2. Build pgvector from source (migrations require `CREATE EXTENSION vector`):
   `git clone --depth 1 --branch v0.8.1 https://github.com/pgvector/pgvector /tmp/pgv && cd /tmp/pgv && make && sudo -n make install`
3. `sudo -n service postgresql start` (Ubuntu creates+starts the `14/main` cluster on :5432)
4. `sudo -n -u postgres psql -c "CREATE ROLE knowledge_graph LOGIN PASSWORD 'local_dev_password' SUPERUSER; CREATE DATABASE knowledge_graph OWNER knowledge_graph;"`
5. `apps/api/.venv/bin/python -m alembic upgrade head` — verify with `select version_num from alembic_version`.

## Session without Google OAuth
- Sign `{"user_id": "<uuid>"}`: `TimestampSigner(SESSION_SECRET)` — **no salt** in the installed starlette version. Cookie = `signer.sign(b64encode(json.dumps(session)))`.
- Serve a tiny page on another localhost port (e.g. :9000) whose JS sets `document.cookie = "kg_session=...; path=/"` then `location.replace("http://localhost:3000")`. Host-scoped cookies reach both :3000 and :8000; SameSite=lax sends them same-site.
- Verify with `curl -H "Cookie: kg_session=..." http://localhost:8000/auth/me`.
- The seeded user also needs an `organizations` row + `organization_memberships` row (role 'admin') or `/auth/me` → `needs_account` → onboarding screen.

## Seeding chat data for the Ask screen
- `chat_messages.citations`/`steps` are NOT NULL with no DB default — raw INSERTs must pass `CAST(:x AS jsonb)` explicitly (also avoids `:param::jsonb` syntax errors).
- Record citation shape: `{record_id, name, stack_type, checked:"person", confirmed_by, confirmed_at, revision, source_ids}` — `record_id` must be a real `substacks.id` or the deep-link chip does nothing.
- Chunk citation shape: `{chunk_id, document_id, title, source, source_uri, snippet}` — arbitrary UUIDs fine.
- `checked_note` is server-computed: `"Confirmed by {by} on {date[:10]}"` when answered + `checked="person"`.
- `answered=false` renders muted-italic text and hides the thumbs buttons.
- For the record chip's deep-link to work, the substack must be visible: `owner_user_id` NULL (workspace scope) or == user.id. Seed `substack_contents` (status 'confirmed', revision 1, `inputs_fingerprint` 64 chars) for non-empty detail.

## Capturing transient pending states
UI states like "Reading sources…" flash too fast locally. Add latency: `sudo -n tc qdisc add dev lo root netem delay 1200ms` before the action, remove with `sudo -n tc qdisc del dev lo root`.

## Window sizing for mobile breakpoints
The Ask view's rail collapses below 900px. `wmctrl -r :ACTIVE:` may hit the wrong window — list with `wmctrl -l` and target the app window by ID: `wmctrl -i -r <id> -b remove,maximized_vert,maximized_horz && wmctrl -i -r <id> -e 0,20,60,680,660`.
