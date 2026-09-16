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
