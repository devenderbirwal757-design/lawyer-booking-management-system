# Lawyer Booking & Management System — Frontend

Next.js 15 (App Router) + TypeScript + Tailwind CSS v4 + shadcn/ui + TanStack Query + RHF + Zod.

See [`frontend-plan.md`](../frontend-plan.md) for the phased implementation plan — every phase in
the checklist (§11) has a backend dependency that must land first. This repo implements the
frontend side of that plan.

## Getting started

```bash
cp .env.example .env.local   # then fill in the values
npm install
npm run dev
```

Open http://localhost:3000. The backend API defaults to `http://localhost:8000/api/v1`.

## Scripts

| Command                | Purpose                                         |
| ---------------------- | ----------------------------------------------- |
| `npm run dev`          | Start the dev server (Turbopack)                |
| `npm run build`        | Production build                                |
| `npm run start`        | Serve the production build                      |
| `npm run lint`         | ESLint                                          |
| `npm run typecheck`    | `tsc --noEmit`                                  |
| `npm run test`         | Vitest unit tests                               |
| `npm run test:watch`   | Vitest watch mode                               |
| `npm run format`       | Prettier write                                  |
| `npm run format:check` | Prettier check                                  |
| `npm run check:bundle` | Per-route JS budget check                       |
| `npm run ci`           | lint → typecheck → test → build → bundle budget |

A pre-commit hook (husky + lint-staged) lints and formats staged files.

## Deploying

The app ships as an OCI image built from the Next.js `standalone` bundle:

```bash
docker compose up --build          # local, production-like
curl http://localhost:3000/api/health
```

Sentry is wired through `@sentry/nextjs` (server, client, and source-map upload)
and stays disabled unless a DSN is set. Full runbook — build args, runtime env,
custom domain + HTTPS, health checks, and rollback — in
[`docs/deployment.md`](./docs/deployment.md).

## Conventions (from frontend-plan.md §3, §7)

- Single typed API client in `lib/api/client.ts`; base URL ends in `/api/v1`.
- Response Zod schemas live in `features/*/schema.ts`; TS types are inferred from them.
- Cache keys are defined once in `lib/api/query-keys.ts`.
- Tokens are HttpOnly cookies set by the backend — JS never reads them, and nothing is stored
  in `localStorage`. Never introduce a token into the client bundle.
- Design tokens (deep navy + warm neutral) are in `app/globals.css`. Light theme only for MVP.
- Forms use RHF + Zod with shadcn's `Field` primitives (`components/ui/field.tsx`).

## Env vars

See `.env.example`. `NEXT_PUBLIC_*` values are compiled into the client bundle, so they are
Docker build arguments in production rather than runtime variables. Razorpay secrets and every
other credential belong in the backend.

## Tests

Vitest + Testing Library run from `tests/unit/`. MSW contract tests arrive with the backend
API phases; Playwright E2E is planned per frontend-plan.md §10.

```bash
npm run test
```
