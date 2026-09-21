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

## AI-Human working style

- Whenever given a prompt, agent is able to ask clarifying questions before implementing task (this is optional)

## Product domain

- Target users: **B2B suppliers and Singapore SMEs with 10–100 staff** whose
  customers submit orders in inconsistent formats such as PO PDFs, WhatsApp
  messages, scanned forms, email attachments, and Drive files. Primary users
  are office administrators, sales coordinators, production planners, and
  business owners.
- Initial industries include precision engineering, manufacturing,
  wholesale/distribution, food supply, and other order-driven B2B suppliers.
  The core problems are duplicate manual entry, missed order changes, outdated
  revisions, fragmented evidence, and operational knowledge held by only one
  or two employees.
- Product workflow: **read → confirm → ask**. Sources produce proposals with
  evidence; people confirm them into checked records; users and authorized AI
  assistants query confirmed records before source material.
- WhatsApp, email, PDFs, and Google Drive are primary knowledge sources. PDPA
  compliance (consent, retention, access control, and audit history) shapes
  ingestion.
- The platform supports two distinct account types: **Personal** and
  **Company/Organization**.
  - A Company/Organization account must be backed by Google Workspace. It has
    one administrator role, assigned to a single user, while every person uses
    their own user account.
  - Within a Company/Organization account, a user's own Stacks correspond to
    their Google Workspace **My Drive**. Other Google **Shared Drives** appear
    as separate Workspaces listed horizontally.
  - Users cannot connect an individual Google account to a Company/Organization
    account. They must create and use a separate Personal account for their
    individual Google account.
- **Stacks** are the core entity model—typed collections into which ingested
  information is filed and linked. The initial 12 Stacks are:
  - **Sales Orders** — customer POs, line items, quantities, revisions, dates
  - **Clients** — customer companies, terms, locations, and account history
  - **Items** — products, SKUs, materials, specifications, and customer codes
  - **Invoices** — sales invoices, GST, payments, credit notes, and InvoiceNow
  - **Suppliers** — material/service vendors, lead times, prices, performance
  - **Supplier Orders** — purchases placed with suppliers or subcontractors
  - **Production Jobs** — work orders, schedules, progress, and blockers
  - **Specifications & Revisions** — drawings, requirements, revision history
  - **Conversations** — WhatsApp/email changes, approvals, and commitments
  - **PICs** — people responsible for each task or decision
  - **Meetings** — meeting notes, action items, and follow-ups
  - **Files** — documents, drawings, images, and attachments
  

## Enhanced Features (not in MVP)
**Company/Organization**. Either type can be created directly by uploading
  files and must work without connecting to or depending on Google.
  - Google Drive and Google Workspace are optional integrations, not account
    creation requirements or the platform's system of record.
  - A Company/Organization account has one administrator role, assigned to a
    single user, while every person uses their own user account.
  - Without Google, uploaded files and the Stacks created from them belong to
    the relevant Personal or Company/Organization workspace.
  - When Google Workspace is connected to a Company/Organization account, a
    user's own Stacks correspond to their Google Workspace **My Drive**. Other
    Google **Shared Drives** appear as separate Workspaces listed horizontally.