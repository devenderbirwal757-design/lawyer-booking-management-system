# Lawyer Booking & Management System

A multi-tenant-ready appointment booking and management system for a legal
practice: public marketing site and service catalogue, phone-OTP customer auth,
a five-step booking wizard with online payment, a customer portal, and a full
admin console for scheduling, payments, reports, and audit.

This repository is **proprietary and not open source** — see [LICENSE](./LICENSE).

## Repository layout

| Path | What it is |
| --- | --- |
| [`backend/`](./backend) | Django 5.2 + DRF API, Celery workers, 13 domain apps |
| [`frontend/`](./frontend) | Next.js 15 (App Router) + React 19 web client |
| [`prd.md`](./prd.md) | Product requirements — the source of truth for scope |
| [`backend-plan.md`](./backend-plan.md) | Backend design, data model, and phase checklist |
| [`frontend-plan.md`](./frontend-plan.md) | Frontend design, layout, and phase checklist |
| [`security.md`](./security.md) | Security requirements and the pre-launch checklist |
| [`scripts/check_docs.py`](./scripts/check_docs.py) | Verifies the docs stay consistent with each other |

Start with `prd.md` for what the system does, then the matching plan for how it
is built.

## Stack

**Backend** — Django 5.2, Django REST Framework, SimpleJWT (JWT auth),
drf-spectacular (OpenAPI), django-filter, Celery + Redis, PostgreSQL with
`btree_gist` (exclusion constraints), structlog, argon2-cffi.

Domain apps: `tenants`, `accounts`, `auth_otp`, `customers`, `services`,
`providers`, `scheduling`, `appointments`, `payments`, `notifications`,
`reminders`, `reports`, `audit`.

**Frontend** — Next.js 15 App Router, React 19, TypeScript (strict), Tailwind
CSS v4, shadcn/ui + Radix, TanStack Query, React Hook Form + Zod, Zustand,
`date-fns` / `react-day-picker`, next-themes, Sentry.

Three notable decisions, each deliberate and argued in `backend-plan.md`:

- **Customer identity is phone + OTP only** — no password, no required email
  (§6.3, decision D3).
- **Slots are spaced by `duration + buffer`,** walked from the start of working
  hours, with no separate interval field (§3.1, decision D4).
- **Payment is online-first via a Razorpay gateway** sitting behind an
  abstraction, so other gateways can be added (§6).

## Getting started

Each subproject has its own README with full setup detail, env var reference,
and command list:

- [`backend/README.md`](./backend/README.md)
- [`frontend/README.md`](./frontend/README.md)

In short:

```bash
# Backend — http://localhost:8000
cd backend
docker compose up --build        # or: pip install -e ".[dev]" && python manage.py runserver

# Frontend — http://localhost:3000
cd frontend
npm ci && npm run dev
```

Copy `.env.example` to `.env` in both directories before running anything.
Real `.env` files are gitignored; only the templates are committed.

## Tests and CI

```bash
cd backend  && pytest            # 424 tests
cd frontend && npm run test      # 63 unit tests
npm run lint && npm run typecheck && npm run build
python3 scripts/check_docs.py    # doc consistency
```

CI ([`.github/workflows/ci.yml`](./.github/workflows/ci.yml)) runs three jobs on
every push: `quality` (ruff lint + format check, mypy strict, no pending
migrations, Django system checks), `test` (migrations against a fresh database,
pytest, coverage), and `frontend` (lint, typecheck, unit tests, build, per-route
bundle budgets, throttled-mobile Lighthouse budget, and Playwright E2E).

A separate [`docs.yml`](./.github/workflows/docs.yml) runs the doc consistency
checker, and `.pre-commit-config.yaml` wires it into local commits.

## Status

Backend phases 0–6 are implemented and tested. Frontend phases 0–8 are
implemented, including the CI-gated Lighthouse budget.

Known gaps, in rough priority order:

- **Backend notifications, reminders, and reports have no test coverage.** The
  code is written and wired into `INSTALLED_APPS`, but their `tests/` packages
  are empty and nothing in `backend/tests/` exercises them.
- **Payment cannot be exercised end to end.** Razorpay test credentials and the
  webhook secret are unset, so the booked-payment → webhook → confirmation flow
  is `test.fixme()` in the E2E suite.
- **`backend/tests/e2e/` is empty.** No full pass against the PRD success
  criteria in staging; blocked on live payment credentials and a public HTTPS
  webhook.
- **Frontend Phase 9 is scaffolding only.** Container and Sentry artifacts
  exist; nothing is deployed.
- **Phase 10 hardening is incomplete** — no backup/restore runbook, no managed
  Postgres deploy config, no load harness, and the `security.md` pre-launch
  checklist is unsigned.

Both `backend-plan.md` and `frontend-plan.md` carry more detail, including
checkboxes and rationale per phase.

## Security

Report vulnerabilities privately to the repository owner rather than opening a
public issue. `security.md` documents the controls implemented and the
pre-launch checklist that has not yet been signed off.