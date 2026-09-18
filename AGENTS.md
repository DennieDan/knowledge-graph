# Project rules

## Environment

- **Use Node 24.** The repo's pnpm requires Node >= 18.12; run `nvm use` (an
  `.nvmrc` is provided) before any pnpm/turbo command.
- Package manager: **pnpm** (via `~/Library/pnpm`). Orchestration: **turbo**.

## Commands

- Dev (all apps): `pnpm run dev` — web:3000, docs:3001, api:8000 (FastAPI
  uvicorn, `apps/api/.venv`)
- Web only: `pnpm dev` in `apps/web`
- Verify web changes: `pnpm check-types` and `pnpm lint` in `apps/web`

## Structure

- `apps/web` — Next.js 16 (App Router, Turbopack), React 19, CSS Modules
- `apps/docs` — Next.js docs app (port 3001)
- `apps/api` — FastAPI service (port 8000)
- `packages/ui`, `packages/eslint-config`, `packages/typescript-config` —
  shared workspace packages (`@repo/*`)

## Conventions

- UI follows Material Design 3. Color tokens live in
  `apps/web/app/globals.css` as `--md-sys-color-*` (palette: #353535,
  #3c6e71, #ffffff, #d9d9d9, #284b63).
- Components live in `apps/web/app/components/` as
  `<name>.tsx` + `<name>.module.css`.

## Product domain

- Target users: **Singapore SMEs**, starting with the **event organisers &
  production houses** vertical (incl. MICE: conferences, exhibitions, D&D).
  WhatsApp + Google Drive are the primary knowledge sources; PDPA
  compliance (consent, retention, access audit) shapes ingestion.
- **Stacks** are the core entity model — typed collections that ingested
  items get filed/linked into (e.g. a WhatsApp thread is filed under its
  Event). The decided set of 10 Stacks:
  - **Clients** — corporate accounts; links to their past events
  - **Events** — master entity; pipeline: pitching → confirmed →
    planning → live → debrief → invoiced
  - **Meetings** — client briefs, WIPs, site recce notes
  - **Vendors** — suppliers (AV, catering, staging); rates + reliability
  - **Contacts** — people: staff and external, with roles
  - **Proposals** — quotes/pitches, costing versions, win/loss
  - **Finance Documents** — invoices, budgets, contracts (InvoiceNow later)
  - **Conversations** — imported WhatsApp threads as first-class records
  - **Crew** — freelancers/event crew: roles, rates, availability
  - **Licenses** — permits per event (PEL/SPF, SCDF TCOUP, AEL/IMDA,
    liquor, NEA food stalls, LTA road closures); expiry/status tracking
  - **Venues** — event venues; contracts, rates, availability
  
