# Turborepo starter

This Turborepo starter is maintained by the Turborepo core team.

## Using this example

Run the following command:

```sh
npx create-turbo@latest
```

## What's inside?

This Turborepo includes the following packages/apps:

### Apps and Packages

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

### Backend setup

Prerequisites: Docker with Compose, Python 3.9+, and the Node/pnpm versions in
`package.json`. Start the local PostgreSQL 18 service (pgvector 0.8.6):

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

Then start all applications with:

```sh
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

Initial schema:

- `organizations`: company/workspace ownership.
- `documents`: organization, title, source, external ID, and source/file URI.
- `document_versions`: revision number, original extracted text, SHA-256 hash,
  and creation time. A document cannot have duplicate revision numbers.
- `chunks`: version reference, ordered text, optional embedding and model ID.
  The model ID is required when an embedding exists.

Foreign keys preserve the source chain and cascade deletions. This is storage
infrastructure: authentication, memberships, document permissions, upload/search
endpoints, and automatic embedding generation are subsequent work. Organization
ownership alone does not enforce access control. Add permission checks before
exposing private document retrieval to users. Future search must restrict both
organization/access and embedding model before ranking.

The initial vector column has **384 dimensions**, provisionally matching
[`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).
No model is downloaded or called in this setup. Confirm the model before ingestion;
changing dimensions requires a migration, and changing models requires re-embedding.
Search initially uses exact cosine distance; no approximate vector index is needed
for the foundation checks. [pgvector documentation](https://github.com/pgvector/pgvector)

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

### Utilities

This Turborepo has some additional tools already setup for you:

- [TypeScript](https://www.typescriptlang.org/) for static type checking
- [ESLint](https://eslint.org/) for code linting
- [Prettier](https://prettier.io) for code formatting

### Build

To build all apps and packages, run the following command:

With [global `turbo`](https://turborepo.dev/docs/getting-started/installation#global-installation) installed (recommended):

```sh
cd my-turborepo
turbo build
```

Without global `turbo`, use your package manager:

```sh
cd my-turborepo
npx turbo build
pnpm exec turbo build
pnpm exec turbo build
```

You can build a specific package by using a [filter](https://turborepo.dev/docs/crafting-your-repository/running-tasks#using-filters):

With [global `turbo`](https://turborepo.dev/docs/getting-started/installation#global-installation) installed:

```sh
turbo build --filter=docs
```

Without global `turbo`:

```sh
npx turbo build --filter=docs
pnpm exec turbo build --filter=docs
pnpm exec turbo build --filter=docs
```

### Develop

To develop all apps and packages, run the following command:

With [global `turbo`](https://turborepo.dev/docs/getting-started/installation#global-installation) installed (recommended):

```sh
cd my-turborepo
turbo dev
```

Without global `turbo`, use your package manager:

```sh
cd my-turborepo
npx turbo dev
pnpm exec turbo dev
pnpm exec turbo dev
```

You can develop a specific package by using a [filter](https://turborepo.dev/docs/crafting-your-repository/running-tasks#using-filters):

With [global `turbo`](https://turborepo.dev/docs/getting-started/installation#global-installation) installed:

```sh
turbo dev --filter=web
```

Without global `turbo`:

```sh
npx turbo dev --filter=web
pnpm exec turbo dev --filter=web
pnpm exec turbo dev --filter=web
```

### Remote Caching

> [!TIP]
> Vercel Remote Cache is free for all plans. Get started today at [vercel.com](https://vercel.com/signup?utm_source=remote-cache-sdk&utm_campaign=free_remote_cache).

Turborepo can use a technique known as [Remote Caching](https://turborepo.dev/docs/core-concepts/remote-caching) to share cache artifacts across machines, enabling you to share build caches with your team and CI/CD pipelines.

By default, Turborepo will cache locally. To enable Remote Caching you will need an account with Vercel. If you don't have an account you can [create one](https://vercel.com/signup?utm_source=turborepo-examples), then enter the following commands:

With [global `turbo`](https://turborepo.dev/docs/getting-started/installation#global-installation) installed (recommended):

```sh
cd my-turborepo
turbo login
```

Without global `turbo`, use your package manager:

```sh
cd my-turborepo
npx turbo login
pnpm exec turbo login
pnpm exec turbo login
```

This will authenticate the Turborepo CLI with your [Vercel account](https://vercel.com/docs/concepts/personal-accounts/overview).

Next, you can link your Turborepo to your Remote Cache by running the following command from the root of your Turborepo:

With [global `turbo`](https://turborepo.dev/docs/getting-started/installation#global-installation) installed:

```sh
turbo link
```

Without global `turbo`:

```sh
npx turbo link
pnpm exec turbo link
pnpm exec turbo link
```

## Useful Links

Learn more about the power of Turborepo:

- [Tasks](https://turborepo.dev/docs/crafting-your-repository/running-tasks)
- [Caching](https://turborepo.dev/docs/crafting-your-repository/caching)
- [Remote Caching](https://turborepo.dev/docs/core-concepts/remote-caching)
- [Filtering](https://turborepo.dev/docs/crafting-your-repository/running-tasks#using-filters)
- [Configuration Options](https://turborepo.dev/docs/reference/configuration)
- [CLI Usage](https://turborepo.dev/docs/reference/command-line-reference)
