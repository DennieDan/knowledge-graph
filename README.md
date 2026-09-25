# crossPOd

**Every order, confirmed in one place.**

crossPOd is a knowledge platform for B2B suppliers and Singapore SMEs. It reads
the purchase orders, WhatsApp messages, scanned forms, email attachments and
Drive files customers already send, proposes structured records with evidence
links, and answers questions from confirmed data. AI proposes — a person
confirms every change.

- **Live app:** https://knowledge-graph-web-sooty.vercel.app
- CS3216 Assignment 3 · Group `asg3-dinh-subramanian-ng-kalent`

## Team

| Matriculation No. | Name | Main contributions |
| ----------------- | ---- | ------------------ |
| EXXXXXXX | Đinh Duy Linh Đan | Repository lead; knowledge pipeline (WhatsApp/Drive ingestion, chunking, embeddings), LLM extraction and generation, Stacks/Substacks API and UI |
| E1121733 | Subramanian Karthikeyan | Marketing landing page, SEO/OG metadata, Vercel deployment configuration; backend API and tests |
| EXXXXXXX | Ng Chen Meng | Backend review/operations stack: findings and checks, background job scheduler, question set, nightly scorer and regression gate, health/Maintenance |
| E1406293 | Kalent Chia Chang Rong | Frontend: Ask chat interface, "To check" review queue, Stacks/substack detail, workspace shell and UI refinement; end-to-end testing |

## What's inside

This Turborepo includes the following packages/apps:

- `web`: the [Next.js](https://nextjs.org/) frontend application
- `api`: the [FastAPI](https://fastapi.tiangolo.com/) backend application
- `docs`: the existing Next.js documentation application
- `@repo/ui`: a stub React component library shared by the Next.js applications
- `@repo/eslint-config`: `eslint` configurations (includes `@next/eslint-plugin-next` and `eslint-config-prettier`)
- `@repo/typescript-config`: `tsconfig.json`s used throughout the TypeScript applications

The frontend applications use [TypeScript](https://www.typescriptlang.org/), while the backend uses Python and FastAPI.

### Application architecture

```text
web (Next.js, http://localhost:3000)
        |
        | REST / SSE
        v
api (FastAPI, http://localhost:8000) ──> WAHA (WhatsApp HTTP API, http://localhost:3100)
```

The backend exposes liveness and database readiness endpoints:

```text
GET /health -> {"status":"ok"}
GET /ready  -> 200 when PostgreSQL, pgvector, and application tables are ready; otherwise 503
```

## Set-up instructions (local testing)

Prerequisites: Docker with Compose, Python 3.9+, Node 24 (`nvm use` reads
`.nvmrc`), and pnpm via corepack.

Start the local PostgreSQL 18 service (pgvector 0.8.6):

```sh
docker compose up -d --wait db
```

Create a virtual environment, install dependencies, configure the backend, and
apply the schema migrations:

```sh
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python -m alembic upgrade head
cd ../..
```

If you already have an `.env`, preserve it and add `DATABASE_URL` from the example.
The checked-in Compose credentials are for local development only. PostgreSQL is
bound to `127.0.0.1:5432`; the named volume preserves data when containers stop or
are recreated. `docker compose down` retains that volume; `down -v` deletes it.
A database already using port 5432 must be stopped, or both the Compose host port
and the backend connection URL must be changed.

Then install JS dependencies and start all applications with:

```sh
pnpm install
pnpm dev
```

The applications run on these ports:

- `web`: http://localhost:3000
- `api`: http://localhost:8000
- `docs`: http://localhost:3001

To run only the backend:

```sh
pnpm --filter api dev
```

The knowledge worker (needed for the in-app "Analyze" pipeline) runs alongside
the API:

```sh
cd apps/api && pnpm worker        # or: .venv/bin/python -m scripts.worker
```

> **Note:** root `pnpm dev` also starts the API via a Unix-only script — use the
> per-app commands above on Windows.

### Sign-in without Google OAuth

Google sign-in requires `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` in
`apps/api/.env`. For local testing without OAuth you can forge a session
cookie — `kg_session` is `itsdangerous.TimestampSigner(SESSION_SECRET).sign(...)`
of a JSON `{"user_id": ...}` payload; see `.agents/skills/testing-knowledge-graph/SKILL.md`.

### WhatsApp setup (WAHA, development only)

WhatsApp import runs through a self-hosted [WAHA](https://waha.devlike.pro/)
container — an **unofficial** WhatsApp Web API, so it is used only for
development on a spare number (bans are possible). Start it and configure the
backend:

```sh
# Apple Silicon: keep gows-arm. x86: omit WAHA_IMAGE_TAG (defaults to gows).
WAHA_IMAGE_TAG=gows-arm WAHA_API_KEY=dev-secret WAHA_DASHBOARD_PASSWORD=devpass \
  docker compose -f apps/api/waha/docker-compose.yml up -d
```

Then set in `apps/api/.env`:

```env
WAHA_BASE_URL=http://localhost:3100
WAHA_API_KEY=dev-secret
# Optional, for live incremental sync (omit for poll-only):
WAHA_WEBHOOK_URL=http://host.docker.internal:8000/whatsapp/webhooks
WAHA_WEBHOOK_SECRET=<random secret>
```

Apply migrations, sign in to the web app, and use **WhatsApp → Connect** to
link a number by QR code or pairing code, then pick chats to import. Full
details, endpoint reference, and testing steps:
[`apps/api/docs/whatsapp.md`](apps/api/docs/whatsapp.md).

### Database development

The browser calls FastAPI; only the backend connects to PostgreSQL. Settings read
`apps/api/.env` regardless of the working directory (also for the built app), and
an exported `DATABASE_URL` overrides the file. No credentials belong in frontend
`NEXT_PUBLIC_*` variables.

### Ingestion

`app/ingest.py` turns connector data into a `Document`, a new `DocumentVersion`,
and its `chunks`. A revision is only written when the SHA-256 of the extracted
text changes, so re-running is a no-op; earlier revisions keep their chunks.
`app/sources.py` normalizes each connector — a WhatsApp chat becomes a
chronological `timestamp speaker: message` transcript (media without a caption
becomes `[image]`), and a Drive file is exported to text (Google editor files via
`files.export`, other text types via `alt=media`; binary types are skipped).
`app/chunking.py` splits on paragraphs, then sentences, and finally into
overlapping windows for unspaced text such as Chinese.

Documents are organization-scoped:

```sh
pnpm --filter api db:ingest -- --organization-id UUID whatsapp --user-email me@example.com
pnpm --filter api db:ingest -- --organization-id UUID drive --user-email me@example.com --file-id ID
```

Ingestion stores chunks without embeddings; run `db:reembed` afterwards to fill
them in.

### Embeddings

`app/embeddings.py` loads the encoder lazily on first use (weights download from
Hugging Face, ~470 MB, cached in `~/.cache/huggingface`) and returns normalized
384-dimensional vectors, so cosine distance is a dot product. E5 is asymmetric:
stored chunk text goes through `embed_passages` (`passage: ` prefix) and search
text through `embed_query` (`query: ` prefix); mixing them up degrades retrieval.
Input is truncated at 512 tokens.

`EMBEDDING_MODEL` and `EMBEDDING_DIMENSIONS` in `app/models.py` are the schema
contract; `EMBEDDING_MODEL`, `EMBEDDING_DEVICE`, and `EMBEDDING_BATCH_SIZE` in
`.env` override the runtime encoder, and startup fails if the configured model's
width does not match the column.

Vectors from different models must never be compared, so after a model change
backfill the chunks left on the old one:

```sh
pnpm --filter api db:reembed -- --dry-run   # count stale chunks
pnpm --filter api db:reembed
```

Run from `apps/api` with the virtual environment active:

```sh
python -m alembic upgrade head
python -m alembic check
python -m unittest discover -s tests -v
```

The integration tests require a migrated database. They verify document round trips,
vector ranking, constraints, and readiness, and roll back their inserted records.
The equivalent workspace scripts are `pnpm --filter api db:migrate`,
`pnpm --filter api db:check`, and `pnpm --filter api test`.

For later schema changes, update `app/models.py`, generate a migration with
`python -m alembic revision --autogenerate -m "describe change"`, review it, then
apply it. Migrations explicitly enable the `vector` extension; the initial downgrade
removes application tables but retains the extension in case other schemas use it.
The migration account needs permission to enable extensions; a production runtime
account should have only the application permissions it needs.

`GET /health` remains independent of PostgreSQL. `GET /ready` returns 503 when
the database is unavailable, the extension is missing, or the expected tables/columns
are absent. Database errors and credentials are not returned to clients.

## Deployment

Production runs on Supabase (Postgres + pgvector), Render (API, worker, WAHA via
the root `render.yaml` Blueprint), and Vercel (web). The web app proxies
`/backend/*` to the API so the session cookie stays first-party. The full
deployment checklist (OAuth redirect URIs, environment variables) lives in
[`AGENTS.md`](AGENTS.md).

## Resources used

- [create-turbo / Turborepo starter](https://turborepo.dev/) — monorepo scaffold, build orchestration, pnpm workspaces
- [Next.js 16](https://nextjs.org/) (App Router, Turbopack) and [React 19](https://react.dev/) — web frontend and landing page
- [Material Design 3](https://m3.material.io/) — design system and color tokens (`--md-sys-color-*` in `apps/web/app/globals.css`)
- [FastAPI](https://fastapi.tiangolo.com/) + [SQLAlchemy](https://www.sqlalchemy.org/) + [Alembic](https://alembic.sqlalchemy.org/) — API, ORM, migrations
- [PostgreSQL](https://www.postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) — storage and vector similarity search
- [sentence-transformers](https://www.sbert.net/) with [`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small) — self-hosted embeddings (model choice: [our survey](docs/research/embedding-model.md))
- [OpenAI API](https://platform.openai.com/) — document analysis, stack discovery and generation, cited chat answers
- [WAHA](https://waha.devlike.pro/) — unofficial WhatsApp Web API sidecar for chat ingestion (development only)
- [Google APIs](https://developers.google.com/) — OAuth sign-in and Drive export (`drive.readonly`)
- [PostHog](https://posthog.com/) — product analytics (first-party `/ingest` proxy)
- [Supabase](https://supabase.com/), [Render](https://render.com/), [Vercel](https://vercel.com/) — production hosting
- [Prettier](https://prettier.io), [ESLint](https://eslint.org), [TypeScript](https://www.typescriptlang.org/) — formatting, linting, type checking
