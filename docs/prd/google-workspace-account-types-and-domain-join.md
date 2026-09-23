# Google Workspace account types and domain-based joining

- **Date:** 2026-09-21
- **Status:** Implemented
- **Branch:** `feat/connect-google-workspace`
- **Related:** Google Drive live-sync scope decision in [`docs/research/drive-scope-and-verification.md`](../research/drive-scope-and-verification.md)

## Context

The product supports two account types:

- **Personal** — for individual users, including users who sign in with a personal Gmail account.
- **Company / Organization** — for teams. A Company account is backed by a Google Workspace domain and has a single administrator role assigned to one user. Every other person uses their own user account.

Previously, users could only join a Company workspace through an explicit admin invitation. This PRD documents the revised behavior that also allows authenticated Google Workspace users to join an existing Company automatically when their hosted domain matches the Company’s registered domain.

## Product decision

The MVP supports **both** ways to get into a Company workspace:

1. **Admin invitation** — an existing Company admin invites a specific user by email.
2. **Automatic domain join** — a Google Workspace user whose `hosted_domain` matches a Company’s `google_domain` is added as a member on sign-in, with no invitation needed.

If no Company exists for the user’s hosted domain, the user may still choose to create either a Personal or a Company account. That choice remains open and is not forced by the system.

## Account type overview

| Account type | Who creates it | Google Workspace required? | Admin count | User accounts |
| --- | --- | --- | --- | --- |
| Personal | Any user | No | 1 (the owner) | Single user |
| Company | A Google Workspace user | Yes | Exactly 1 | Each member uses their own user account |

A Company is tied to a single Google Workspace domain (`google_domain`). Multiple Companies cannot share the same domain.

## Automatic domain join

When a signed-in user calls `GET /auth/me`, the backend evaluates whether they should be auto-joined to an existing Company workspace.

### Conditions for auto-join

1. The user has a Google Workspace `hosted_domain` (i.e., not a personal `@gmail.com` account).
2. The user currently has **no** organization memberships.
3. A Company organization exists whose `google_domain` equals the user’s `hosted_domain`.

### Result

- The user is added to that Company as a `member`.
- The new membership becomes the user’s active account.
- Existing members and users who already have any membership are not processed again.

### Why this is lazy

The check happens inside `/auth/me`, not during the OAuth callback. This means it also handles users who created an account **before** the Company workspace for their domain existed. The next time they call `/auth/me` after a Company has been created, they are joined automatically.

## Duplicate Company prevention

To enforce the one-Company-per-domain rule, the backend rejects attempts to create a second Company for the same Google Workspace domain.

### API behavior

- `POST /accounts` returns HTTP `409 Conflict` with detail `company_domain_taken` when a Company already exists for the user’s hosted domain.
- The frontend onboarding flow maps this error to a user-friendly message asking the user to request an invitation from their Company admin.

### Database enforcement

- Migration `0007_unique_company_domain` adds a partial unique index on `organizations.google_domain` where `account_type = 'company'`.
- The SQLAlchemy model includes the matching partial unique index.
- The database-level constraint prevents duplicate domains even under concurrent requests.

## Frontend behavior

| Scenario | What the user sees |
| --- | --- |
| User signs in with a Workspace domain that already has a Company | Auto-joined as a member; onboarding is skipped. |
| User signs in with a Workspace domain that has no Company | The onboarding choice between Personal and Company remains available. |
| User tries to create a Company for a domain that already has one | Error message: ask the Company admin for an invitation. |

## Technical implementation notes

### Endpoints changed

- `GET /auth/me` — added lazy auto-join logic.
- `POST /accounts` — added duplicate-domain validation before Company creation.

### Database changes

- Migration: `apps/api/migrations/versions/0007_unique_company_domain.py`
- Partial unique index on `organizations.google_domain` for `account_type = 'company'`.

### Data cleanup performed during development

The development database initially contained two Company organizations for `dandinh.net`:

| Organization | ID | Action |
| --- | --- | --- |
| `My Company` | `e848e8f3-87c7-4b88-8e52-0520dea2803c` | Deleted (had only the creator admin, no Drive connections/workspaces/documents/invitations) |
| `Studio North` | `896a177c-5aaf-4c3c-8143-7892f26c5c0d` | Kept as the canonical Company |

The user `dinhduylinhdan@dandinh.net` was moved into the canonical Company as a `member`. Migration `0007` then applied successfully.

## Testing and acceptance criteria

- [x] Duplicate Company creation for an existing domain returns `409 company_domain_taken`.
- [x] A Workspace user with no memberships auto-joins the matching Company through `GET /auth/me`.
- [x] Users who already have memberships are not auto-joined again.
- [x] Database migration applies cleanly and `alembic check` passes.
- [x] Relevant backend tests pass.
- [x] Web checks pass: `pnpm check-types`, `pnpm lint`, `pnpm build`.

## Known limitations and future work

- The current implementation still requests the broad `drive.readonly` OAuth scope. The new selection controls what the application stores and exposes to ingestion, but it does not restrict the OAuth-level permission. A future architecture change could move to `drive.file` plus Google Picker for provider-level restricted access.
- Four embedding tests remain unrelated failures because `sentence_transformers` is not installed in the virtual environment.

## Changelog

- Added automatic domain-based joining for Google Workspace users.
- Added duplicate-Company-domain prevention with database-level constraint.
- Added `409 company_domain_taken` error handling in frontend onboarding.
