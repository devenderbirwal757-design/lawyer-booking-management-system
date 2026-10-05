# Lawyer Booking & Management — Backend

Django 5.2 (LTS) + DRF + PostgreSQL + Celery/Redis implementation of
[`../backend-plan.md`](../backend-plan.md), built from the PRD in
[`../prd.md`](../prd.md).

**Status: Phases 1–6 complete** (tenants & admins, services, providers &
availability, customers & phone-OTP auth, booking, payments). The project
boots, migrations apply, the API is versioned and documented, and the shared
`common/` layer is covered by tests. Notifications (Phase 7) and reminders
(Phase 8) still arrive — see the plan's phase table for the order.

---

## Stack

| Concern | Choice |
| --- | --- |
| Framework | Django 5.2 LTS, Python 3.12+ |
| API | DRF 3.18, versioned under `/api/v1/` |
| Schema | drf-spectacular → `/api/schema/` (Swagger UI at `/api/docs/` in dev) |
| Database | PostgreSQL 16 (required — the double-booking guarantee is a GiST exclusion constraint) |
| Cache / broker | Redis 7 |
| Background jobs | Celery 5.6 + django-celery-beat |
| Auth | Argon2 password hashing, SimpleJWT (admins, Phase 1), phone OTP (customers, Phase 4) |
| Logging | structlog (JSON in prod) with `X-Request-ID` context |
| Quality | ruff, mypy (strict), pytest, pytest-django, factory-boy, freezegun |

Every dependency is pinned to an exact version in `pyproject.toml`.

---

## Repository layout

```
backend/
├── config/                     settings/{base,dev,test,prod}.py, urls, celery, wsgi/asgi
├── apps/                       12 domain apps (tenants … audit) — Phase 0 skeletons
├── common/                     shared API plumbing (see below)
├── tests/
│   ├── testapp/                test-only tenant-scoped model + viewset
│   ├── unit/  integration/  e2e/  factories/
├── scripts/                    create_admin, wait_for_services, seed_demo*, reconcile_payments*
├── .github/workflows/ci.yml
├── pyproject.toml              deps + ruff/mypy/pytest/coverage config
├── Dockerfile
└── docker-compose.yml
```

### What lives in `common/`

| Module | Responsibility |
| --- | --- |
| `querysets.py` | `TenantScopedQuerySet` / `TenantScopedManager` — the single seam that stops cross-tenant reads; raises `TenantContextMissing` instead of returning all rows |
| `mixins.py` | `TenantFilterMixin` — forces every viewset queryset into the current tenant |
| `viewset.py` | `TenantScopedViewSet` (shared behaviour), `BaseViewSet` (CRUD), `ReadOnlyModelViewSet` |
| `exceptions.py` | `{"error": {code, message, details}}` envelope + domain exception classes |
| `permissions.py` | `IsAdmin`, `IsTenantMember` — no ad-hoc `if` in views |
| `throttles.py` | `anon`, `user` and the scoped rates for otp / login / booking / webhook |
| `pagination.py` | `StandardPagination` (page size capped at 100) |
| `idempotency.py` | `Idempotency-Key` validation, `ActorStampMixin`, request-id access |
| `middleware.py` | `RequestIDMiddleware` — request id in, out, and into every log line |
| `utils/timezones.py` | the one place UTC ⇄ tenant-local conversion happens |
| `models.py` | `BaseModel` (UUID pk + `created_at`/`updated_at`) |
| `views.py` | `/healthz` (liveness) and `/readyz` (PostgreSQL + Redis) |

---

## Local setup (macOS / Linux, no Docker)

### 1. Prerequisites

- Python 3.12+ (3.14 is fine)
- PostgreSQL 14+ with `btree_gist` available
- Redis 7+

```bash
brew install postgresql@16 redis          # macOS
brew services start postgresql@16 redis
```

### 2. Database and extensions

```bash
createuser --createdb lawyer_app                     # password: lawyer_app
createdb -O lawyer_app lawyer
createdb -O lawyer_app lawyer_test
psql -d lawyer      -c "CREATE EXTENSION IF NOT EXISTS btree_gist;"
psql -d lawyer_test -c "CREATE EXTENSION IF NOT EXISTS btree_gist;"
```

`btree_gist` is required from Phase 5 onwards: the anti-double-booking
exclusion constraint is built on it. `pg_trgm` (admin search) is added in
Phase 2.

### 3. Python environment

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # then edit DJANGO_SECRET_KEY
```

### 4. Run

```bash
python manage.py migrate
python manage.py createsuperuser --noinput --email admin@example.com
python manage.py runserver
```

Celery tasks run **inline** in dev (`DJANGO_CELERY_TASK_ALWAYS_EAGER=True` in
`.env.example`) so a single process is enough. To use a real worker instead:

```bash
DJANGO_CELERY_TASK_ALWAYS_EAGER=False python manage.py runserver
celery -A config worker -l info
celery -A config beat -l info
```

### Useful URLs

| URL | Purpose |
| --- | --- |
| `/healthz` | liveness — no dependencies touched |
| `/readyz` | readiness — checks PostgreSQL and Redis, 503 if degraded |
| `/api/schema/` | OpenAPI 3 document |
| `/api/docs/` | Swagger UI (dev/test only) |
| `/admin/` | Django admin |

---

## Local setup with Docker

```bash
cd backend
cp .env.example .env
docker compose up --build
```

Brings up `api` (gunicorn on :8000), `worker`, `beat`, `db`, `redis` and
`mailhog` (web UI on <http://localhost:8025>). Migrations run automatically on
API start; `btree_gist`/`pg_trgm` are created by
`scripts/postgres/init/01-extensions.sql` on first boot.

---

## Everyday commands

```bash
pytest                                    # whole suite
pytest -m unit                            # no database
pytest tests/integration -q
pytest --cov --cov-report=term-missing    # coverage report

ruff check . && ruff format --check .
mypy apps common config

python manage.py makemigrations --check --dry-run
python manage.py check --deploy --settings=config.settings.dev
```

CI (`.github/workflows/ci.yml`) runs exactly these four gates in order:
**lint → typecheck → migrate-check → test**, against a real PostgreSQL
service.

### Tenant resolution checks

`manage.py check` reports `tenants.W001` when `DJANGO_DEFAULT_TENANT_SLUG` is
unset, and **errors** (`tenants.E001` / `tenants.E002`, non-zero exit, refuses to
boot) when it is set to a slug that no practice has or to a suspended practice.
Unset is a warning rather than an error because subdomain and `X-Tenant-Slug`
routing need no default; a default that cannot resolve is broken everywhere, so
it blocks. CI runs `check --deploy --fail-level ERROR`, which fails on E001/E002
and still passes on W001.

Worth knowing why this is a check and not a test: the unset failure is quiet.
`TenantFilterMixin` answers tenant-scoped lists with `qs.none()`, so
`GET /api/v1/services/` returns `200` with `count: 0` against a database full of
services. Nothing in the response distinguishes "no tenant bound" from "this
practice has nothing to sell".

---

## Environment variables

All variables are read through `django-environ` and declared with defaults in
`config/paths.py`. The settings module is chosen by
`DJANGO_SETTINGS_MODULE_SHORT` (`dev` | `test` | `prod`); an explicit
`DJANGO_SETTINGS_MODULE` always wins.

`.env` is read from the repo root if present, otherwise from `backend/`.

### Core

| Variable | Default | Notes |
| --- | --- | --- |
| `DJANGO_SETTINGS_MODULE_SHORT` | `dev` | `dev`, `test`, `prod` |
| `DJANGO_SECRET_KEY` | — | **required in prod**, must be ≥ 50 chars |
| `DJANGO_DEBUG` | `False` | must be `False` in prod |
| `DJANGO_ALLOWED_HOSTS` | `[]` | required in prod |
| `DJANGO_LOG_LEVEL` | `INFO` | |
| `DJANGO_LOG_JSON` | `True` | human-readable console logs when `False` |
| `DJANGO_SERVE_API_DOCS` | = `DEBUG` | Swagger UI toggle |

### PostgreSQL

| Variable | Default |
| --- | --- |
| `DJANGO_DB_NAME` | `lawyer` |
| `DJANGO_DB_USER` | `lawyer_app` |
| `DJANGO_DB_PASSWORD` | `lawyer_app` |
| `DJANGO_DB_HOST` | `127.0.0.1` |
| `DJANGO_DB_PORT` | `5432` |
| `DJANGO_DB_CONN_MAX_AGE` | `60` |
| `DJANGO_DB_SSLMODE` | `prefer` (`require` in prod) |
| `DJANGO_TEST_DB_NAME` | `lawyer_test` |

### Redis / Celery

| Variable | Default |
| --- | --- |
| `DJANGO_CACHE_URL` | `redis://127.0.0.1:6379/0` |
| `DJANGO_CELERY_BROKER_URL` | `redis://127.0.0.1:6379/1` |
| `DJANGO_CELERY_RESULT_BACKEND` | `redis://127.0.0.1:6379/2` |
| `DJANGO_CELERY_TASK_ALWAYS_EAGER` | `True` in dev, `False` in prod |
| `DJANGO_CELERY_TASK_EAGER_PROPAGATES` | `True` |

### Email

| Variable | Default |
| --- | --- |
| `DJANGO_EMAIL_BACKEND` | console (dev) / SMTP (prod) |
| `DJANGO_DEFAULT_FROM_EMAIL` | `no-reply@example.com` |
| `DJANGO_EMAIL_HOST` / `_PORT` / `_USE_TLS` | `mailhog` / `1025` / `False` |

### Security

| Variable | Default |
| --- | --- |
| `DJANGO_CORS_ALLOWED_ORIGINS` | `[]` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `[]` |
| `DJANGO_SECURE_SSL_REDIRECT` | `False` (`True` in prod) |
| `DJANGO_USE_TLS` | `False` — switches default storage to S3 |
| `DJANGO_ACCESS_TOKEN_LIFETIME_MINUTES` | `15` (S §A2: ≤ 15) |
| `DJANGO_REFRESH_TOKEN_LIFETIME_DAYS` | `7` (S §A2: ≤ 7) |

### Throttling

| Scope | Default | Applies to |
| --- | --- | --- |
| `DJANGO_THROTTLE_ANON_RATE` | `60/min` | unauthenticated requests |
| `DJANGO_THROTTLE_USER_RATE` | `600/min` | authenticated requests |
| `DJANGO_THROTTLE_OTP_REQUEST_RATE` | `5/hour` | `POST /auth/otp/request` (Phase 4) |
| `DJANGO_THROTTLE_OTP_VERIFY_RATE` | `20/hour` | `POST /auth/otp/verify` (Phase 4) |
| `DJANGO_THROTTLE_LOGIN_RATE` | `5/15min` | `POST /auth/admin/login` — per IP and per email (S §A2) |
| `DJANGO_THROTTLE_BOOKING_RATE` | `10/min` | `POST /appointments` (Phase 5) |
| `DJANGO_THROTTLE_AVAILABILITY_RATE` | `120/min` | `GET /availability/slots`, `/availability/dates` — stops full-schedule scraping (S §A7) |
| `DJANGO_THROTTLE_WEBHOOK_RATE` | `120/min` | `POST /payments/webhook` (Phase 6) |

### Storage (S3 / MinIO)

`DJANGO_STORAGE_BACKEND`, `DJANGO_AWS_ACCESS_KEY_ID`,
`DJANGO_AWS_SECRET_ACCESS_KEY`, `DJANGO_AWS_STORAGE_BUCKET_NAME` (required in
prod), `DJANGO_AWS_S3_REGION_NAME`, `DJANGO_AWS_S3_ENDPOINT_URL`,
`DJANGO_AWS_QUERYSTRING_AUTH`, `DJANGO_AWS_S3_CUSTOM_DOMAIN`.

### Domain defaults (Phases 3–5)

`DJANGO_DEFAULT_TENANT_SLUG` (`demo`), `DJANGO_DEFAULT_TIMEZONE` (`Asia/Kolkata`),
`DJANGO_DEFAULT_CURRENCY` (`INR`), `DJANGO_SLOT_HOLD_MINUTES` (`10`),
`DJANGO_BOOKING_LEAD_TIME_HOURS` (`2`), `DJANGO_BOOKING_LOOKAHEAD_DAYS` (`60`).

| Variable | Default | Notes |
| --- | --- | --- |
| `DJANGO_DEFAULT_TENANT_SLUG` | `demo` | **The practice served when a request carries no tenant of its own.** `TenantMiddleware` identifies a practice from the host subdomain (`alice.lawyer.test`) or the `X-Tenant-Slug` header; with neither, nor this setting, it binds nothing and every tenant-scoped endpoint degrades silently — `GET /services/` returns `200` with zero rows, `POST /payments/create-order/` returns `500`. Set it for any single-tenant install on a bare domain (localhost, `lawyer.example.com`); leave it empty only if every request is addressed by subdomain. Must match the slug `scripts/seed_demo.py` creates — that script falls back to this value, then to `demo` |
| `DJANGO_CANCELLATION_POLICY_MIN_HOURS` | `0` (no window) | client cancellations *and* reschedules of a `CONFIRMED` appointment are refused this close to the start (`409 cancellation_window`); admin moves are exempt |
| `DJANGO_MAX_ACTIVE_HOLDS_PER_CUSTOMER` | `5` | unpaid `PENDING_PAYMENT` holds per customer (`409 hold_limit_reached`). A throttle bounds rate; this bounds inventory (S §A7) |

### OTP (Phase 4)

| Variable | Default | Notes |
| --- | --- | --- |
| `DJANGO_OTP_LIFETIME_MINUTES` | `5` | code expiry (S §A3) |
| `DJANGO_OTP_MAX_ATTEMPTS` | `5` | wrong guesses before a code is invalidated |
| `DJANGO_OTP_SMS_BACKEND` | `console` | `console` prints the code to stdout; production backend wires the SMS provider |
| `DJANGO_DEFAULT_COUNTRY_CODE` | `+91` | used to normalise national-form numbers to E.164 |

### Payments (Phase 6)

| Var | Default | Purpose |
| --- | --- | --- |
| `DJANGO_PAYMENT_GATEWAY` | `razorpay` | Vendor name. Only `razorpay` is implemented; `cashfree` is a stub that raises, and any other name is a startup error. Outside `DEBUG` a stub gateway refuses to load |
| `DJANGO_PAYMENT_MODE` | `test` | Razorpay's `test`/`live`. A webhook is applied only when its payload mode matches the order's, so a `test` event cannot confirm a `live` order or the reverse |
| `DJANGO_RAZORPAY_KEY_ID` | — | Public key id; `create-order` and all read-backs |
| `DJANGO_RAZORPAY_KEY_SECRET` | — | Signs checkout-session verification and every API read |
| `DJANGO_RAZORPAY_WEBHOOK_SECRET` | — | HMAC secret for the webhook. Required: without it there is no signature to verify and the endpoint is refused |
| `DJANGO_PAYMENT_RECONCILE_MINUTES` | `30` | How old an open order must be before the hourly sweep queries the gateway about it |
| `DJANGO_THROTTLE_PAYMENT_RATE` | `30/min` | Customer `create-order` / `status` |

`python scripts/reconcile_payments.py [--minutes N] [--json]` runs the same
sweep as the beat task by hand, after a gateway outage or when an operator
wants to confirm nothing is stuck. It only downgrades an order to `FAILED` or
confirms one through `mark_captured`; it never invents a success, so running
it repeatedly is safe.

---

## Error envelope

Every non-2xx API response has the same shape:

```json
{
  "error": {
    "code": "slot_unavailable",
    "message": "That time slot is no longer available.",
    "details": null
  }
}
```

`code` is stable and safe to branch on in a client. Domain codes already
defined in `common/exceptions.py`: `validation_error`, `not_found`,
`unauthenticated`, `permission_denied`, `conflict`, `integrity_error`,
`throttled`, `slot_unavailable`, `invalid_state_transition`,
`service_disabled`, `invalid_signature`, `tenant_context_missing`,
`internal_error`.

`tenant_context_missing` (500) is the one 500 that names its own cause: it means
the request reached a tenant-scoped query with no practice bound, which is a
server misconfiguration rather than a bug in the endpoint, and the fix is
`DJANGO_DEFAULT_TENANT_SLUG`. Every other unhandled exception is still collapsed
to `internal_error` / "An unexpected error occurred." so real bugs do not leak
configuration detail to clients.

List endpoints return:

```json
{ "count": 0, "page": 1, "page_size": 20, "num_pages": 1,
  "next": null, "previous": null, "results": [] }
```

---

## Tests

```
tests/unit/          no database — slot maths, policies, signatures, envelopes
tests/integration/   real PostgreSQL, HTTP in and out
tests/e2e/           full PRD flows (Phase 5+)
tests/testapp/       test-only tenant-scoped model proving the common/ seams
```

Tests run against **real PostgreSQL** (not SQLite): the anti-double-booking
exclusion constraint from Phase 5 cannot be expressed in SQLite, and testing
against a different database than production is how that class of bug slips
through.

`tests/testapp` provides a minimal tenant-scoped `Widget` model, its
migration and a `WidgetViewSet`, registered only in
`config/settings/test.py`. It exists so the Phase 0 seams
(`TenantScopedManager`, tenant-filtered viewsets, soft delete, the error
envelope, cross-tenant 404s) are verified against a real database rather than
mocks. It is not part of any runtime settings module.

### The tenant-isolation guard

`tests/unit/test_tenant_queryset_guard.py` fails the build when a tenant-scoped
viewset overrides `get_queryset()` without calling `super()`. That override drops
`TenantFilterMixin`'s filter, so the endpoint reads the whole table — the bug
class behind the cross-tenant admin refund/schedule defect. It looks like
ordinary narrowing in review, so it is enforced mechanically:

```python
class AdminServiceViewSet(BaseViewSet):
    def get_queryset(self):
        qs = super().get_queryset()  # required
        return qs.filter(status=ServiceStatus.ACTIVE)
```

Tenancy is decided from the real `__mro__`, and an override is only the class's
own `__dict__` entry, so import aliases and inheritance depth cannot fool it.

A class whose model has no `tenant` column — `filter(tenant_id=...)` would raise
`FieldError` — must scope itself by hand and declare the reason **in its own
body**, which is how `AdminPaymentEventViewSet` stays exempt while joining
through `gateway_order_id`. Reasons are read from the class's own `__dict__`, so
a stale one cannot excuse a new bypass, and whitespace does not count as a
reason.

Two properties make the guard worth trusting: it is fail-closed (unreadable or
unparseable source is a violation, not a skip), and its detector is pinned
against known-bad and known-good source. Both existed because writing it wrong
was possible — during development it briefly scanned **zero** viewsets (it
subclass-tested DRF's concrete `ViewSet`, which `GenericViewSet` does not inherit
from) while every scan-based test passed vacuously.

### Why `filterset_fields` is banned

`tests/unit/test_filterset_guard.py` fails the build if a tenant-scoped viewset
declares `filterset_fields` or `filterset_class`. Use `_filter_params()` in
`apps/payments/views.py` instead: it validates in the viewset and rejects an
unsupported value with a 400 rather than returning a silently empty page.

Two hazards, both reproduced against the installed django-filter in
`tests/integration/test_filterset_hazard.py` rather than assumed:

| Hazard | What actually happens |
| --- | --- |
| Discloses other practices | A relation field becomes a `ModelChoiceFilter` whose choices come from the **related** model's `_default_manager`. `filterset_fields = ["tenant"]` on `Provider` publishes every practice's slug and UUID to a caller who may only see their own — and puts them in the OpenAPI schema. **Rows stay correctly scoped; this is disclosure, not row leakage.** |
| Needs a bound tenant to exist | Building the filterset introspects `Model._default_manager`, the tenant-scoped manager, raising `TenantContextMissing` inside `AutoFilterSet.get_filters()` — before anything is filtered. It takes down every list request, and `manage.py spectacular`, which has no request and so no tenant. |

`DjangoFilterBackend` deliberately stays in `DEFAULT_FILTER_BACKENDS`. Removing
it would make a future `filterset_fields` silently filter nothing, which is worse
than the loud failure the ban produces.

Those hazard tests assert third-party behaviour on purpose: if a django-filter
upgrade ever stops disclosing related models, they fail, and that is the signal
to revisit the ban rather than a nuisance to suppress.

Useful markers: `-m unit`, `-m integration`, `-m e2e`, `-m concurrency`,
`-m celery`.

---

## What Phase 1 has added on top of Phase 0

- `Tenant` model + `TenantMiddleware` / `get_current_tenant()` (S §A4).
- `User.role`, `User.tenant`, `IsAdmin`, and the JWT auth endpoints
  (`/api/v1/auth/admin/login|refresh|logout`, `GET /me`) with refresh-family
  reuse detection and per-IP/per-email throttling (S §A2).
- The `audit` app: `AuditLog`, the `audit()` helper and `@audited` decorator,
  wired into the user admin as the Phase 1 proof.
- Django admin registration for tenants, users, refresh sessions and the
  (read-only) audit log.
- `seed_demo` creates the default tenant + an owner admin + a default provider
  (`scripts/seed_demo.py`, idempotent). Service and availability rows are
  added via the Django admin.
- `reconcile_payments` is a placeholder here; Phase 6 replaces it with the real
  sweep (see *What Phase 6 has added*).

## What Phase 2 has added on top of Phase 1

- `Service` (`apps/services`): tenant-scoped, price as `Decimal` + ISO
  currency, per-tenant unique auto-slug, duration/buffer bounds, and a
  `status` soft-delete (`DELETED` hides everywhere; PROTECT + the API's
  soft-delete mean a service is never hard-deleted once bookings reference it
  — S §A8 rejects zero/negative price and out-of-range durations).
- `GET /api/v1/services` + `GET /api/v1/services/{slug}` (public, `ACTIVE`
  rows of the request's tenant only) and `GET/POST/PATCH/DELETE
  /api/v1/admin/services` (admin CRUD via `CanEditService`, tenant derived
  from the JWT, never from the payload). Prices are surfaced both raw
  (`price_amount`) and formatted (`price`, e.g. `₹500`) via
  `common/money.py`.
- Django admin registration for services, with the same audit wiring as the
  user admin (every save lands in `AuditLog`); admin delete is disabled.
- Phase 2 tests: public listing hides inactive/deleted and other tenants'
  services; cross-tenant admin access is a 404; `status=DELETED` cannot be
  set via PATCH; soft-delete leaves the row intact.

## What Phase 3 has added on top of Phase 2

- `Provider` (`apps/providers`): the person whose calendar is bookable,
  tenant-scoped with `is_active` as the soft-delete flag. `Service.provider`
  binds a service to its provider (validated to the tenant, never another
  practice's).
- `AvailabilityRule` + `AvailabilityException` (`apps/scheduling`): the
  recurring week (one row per `(provider, weekday)` window, with an optional
  effective date range and **no interval field** — D4) and one-off days
  (`OVERRIDE` replaces the week, `BLOCKED` cuts a window). Both models carry
  no `tenant_id`; isolation flows through `provider__tenant_id`.
- `SlotService` (`apps/scheduling/service.py`): the server-side slot engine.
  Per day it takes `rules ∪ override − blocked − busy`, walks from each window
  start in `duration + buffer_after` steps, and keeps a start only when
  `start + duration <= window_end`. The final slot of the day is never
  truncated when its buffer overruns closing time. Results are cached in
  Redis briefly, keyed by provider+service+date, and invalidated when a rule
  or exception changes; appointment-bearing (`busy`) lookups skip the cache.
  The engine re-runs at Phase 5 booking time — the client can never pick a
  time that the server would not offer.
- `GET /api/v1/availability/slots?service_id=&date=` and
  `GET /api/v1/availability/dates?service_id=&month=` (public, tenant-scoped,
  throttled at `DJANGO_THROTTLE_AVAILABILITY_RATE` to stop full-schedule
  scraping — S §A7).
- `GET/POST/PATCH /api/v1/admin/availability/rules` and
  `GET/POST/DELETE /api/v1/admin/availability/exceptions` (admin calendar
  CRUD; rules reject `end <= start` and same-weekday overlaps; exceptions
  hard-delete on revoke). Both are tenant-isolated through the provider join.
- Django admin registration for providers, rules and exceptions, with the
  same `AuditLog` wiring as earlier models (rules/administrative deletes are
  not hard-deletes).
- Phase 3 tests: the D4 grid contracts (PRD 10:00–13:00 / 30-min →
  10:00…12:30; 45-min(+5) → 10:00/10:50/11:40; 60-min never offers 12:30;
  final-slot buffer overrun), exceptions, busy spans, tenant TZ correctness,
  lead time / horizon, rule overlap validation, cache invalidation, the
  public slots/dates endpoints, admin calendar CRUD with cross-tenant 404s +
  `provider__tenant_id` isolation, and the availability throttle wiring.

## What Phase 4 has added on top of Phase 3

- `Customer` (`apps/customers`): the client principal. Tenants own their
  customers; `phone` is the E.164 identity key, unique per tenant, and `email`
  is optional and unique per tenant *when set* (D3). Reads fail closed with
  `TenantContextMissing`, like every other tenant-scoped model.
- `apps/customers/phone.py`: a dependency-free E.164 normalizer — `+91 98765
  43210`, `91 98765 43210` and `0 98765 43210` all collide onto
  `+919876543210`, so the same person can never be split across spellings
  (S §A3). Invalid and out-of-range numbers are rejected.
- `PhoneOtp` (`apps/auth_otp`): codes are **salted SHA-256 hashes at rest**
  (never plaintext), expire after `DJANGO_OTP_LIFETIME_MINUTES`, and a maximum
  of `DJANGO_OTP_MAX_ATTEMPTS` wrong guesses invalidates the code. Send
  windows (3/15 min, 10/hour per number) are counted on the OTP rows
  themselves, so they hold across restarts and are verifiable from the DB.
- `POST /api/v1/auth/otp/request` and `POST /api/v1/auth/otp/verify`: the
  first always answers `{"ok": true}` — identical for known and unknown
  numbers so it cannot enumerate customers — and is throttled at
  `DJANGO_THROTTLE_OTP_REQUEST_RATE`. Verify exchanges a code for a
  customer-scoped JWT pair and auto-provisions the customer; every code
  failure parses to the same 400 `invalid_otp`.
- `GET /api/v1/auth/me` became the polymorphic `/me`: an admin token gets the
  admin profile, a customer token gets the customer profile. The two scopes
  never cross: `AdminJWTAuthentication` (now the global default) rejects any
  `customer`-scoped token on admin endpoints with 401 instead of crashing on
  the UUID `user_id`, and `CustomerJWTAuthentication` only ever accepts
  `customer`-scoped tokens (S §A3).
- The console OTP backend prints `[dev-otp] OTP for +91…: 123456` to stdout —
  the code never touches a logger, Sentry, or an error report.
- Django admin registration for customers (audit-wired, soft-delete) and a
  read-only OTP code view for the security review.
- Phase 4 tests: the E.164 convergences/rejections, hashing at rest, expiry,
  attempt lockout, both send windows, verify happy path + blank-profile
  preserve, wrong-tenant isolation, identical non-enumerating request
  responses, 404 without a tenant, a verified code never crossing tenants, the
  log-immunity assertion, and the customer-token-vs-admin-endpoint rejection.
## What Phase 5 has added on top of Phase 4

- `Appointment` + `AppointmentStatusHistory` (`apps/appointments`): a booking is
  a hold that becomes an appointment. `PENDING_PAYMENT` and `CONFIRMED` are the
  only *active* statuses — they are what the exclusion constraint and the
  availability engine treat as occupied. `AppointmentStatusHistory` is the
  audit trail: every transition records `from`/`to`, the actor
  (`customer`/`admin`/`system` + id) and a note, and nothing may edit or delete
  a leg after the fact.
- `apps/appointments/state.py`: the legal-transition table, in one place.
  Terminal states (`CANCELLED`, `EXPIRED`, `RESCHEDULED`, `COMPLETED`,
  `NO_SHOW`) are terminal, and a same-status transition is rejected rather than
  silently re-run. No view writes `status` directly.
- `apps/appointments/services.py`: booking is *revalidation*, not a row insert.
  The client's slot is re-derived from the provider's rules, exceptions, live
  appointments and lapsed holds, and the server's duration/price win. A hold
  expires after `DJANGO_SLOT_HOLD_MINUTES`; a paid service also gets a
  `PaymentOrder` in the same transaction.
- Double booking is prevented twice on purpose: the service answers
  `409 slot_unavailable`, and `appointments/migrations/0002_no_provider_overlap.py`
  installs a `btree_gist` exclusion constraint on
  `(provider_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&) WHERE status IN
  ('PENDING_PAYMENT', 'CONFIRMED')`. `end_at` excludes the buffer (turnaround,
  not billable time) while the busy span availability subtracts includes it.
  A losing insert is translated into the same 409 whether PostgreSQL reports an
  `IntegrityError` *or* aborts the transaction with a deadlock/serialisation
  failure while ordering the two index probes — a real race is never a 500.
- `POST /api/v1/appointments` (customer JWT) creates a hold and takes an
  optional `Idempotency-Key` (UUID; a replay answers `200` with the original
  body instead of carving a second appointment). `GET /api/v1/appointments/{id}`
  is owner-scoped.
- `GET /api/v1/me/appointments` is the client dashboard: `upcoming` / `past` /
  `cancelled` buckets, detail with the full status history, plus
  `cancel` and `reschedule`. Every read resolves through
  `customer=request.customer`, so another customer's appointment is a **404,
  never a 403** (S §A4). A client-side cancel *or reschedule* of a confirmed
  appointment is refused inside `DJANGO_CANCELLATION_POLICY_MIN_HOURS`
  (`409 cancellation_window`) — a move is a cancel plus a rebook, so it cannot
  be used to route around the policy.
- `GET /api/v1/admin/appointments` takes the PRD §15 filters (date, status
  including `active`, service, customer, payment status) and `q` search; an
  unknown filter value returns an empty set rather than an unfiltered list.
  `PATCH` is **notes-only** — a `PATCH status=…` is rejected with 400, and the
  lifecycle runs through the `confirm` / `cancel` / `complete` / `no-show` /
  `reschedule` actions. A *paid* service cannot be confirmed by hand until its
  payment lands (open Q6; Phase 6 wires the webhook).
- Hold abuse is bounded on two axes: `DJANGO_THROTTLE_BOOKING_RATE` bounds how
  fast, and `DJANGO_MAX_ACTIVE_HOLDS_PER_CUSTOMER` bounds how many unpaid holds
  can be left dangling at once (`409 hold_limit_reached`) — a throttle alone
  cannot stop a patient client from squatting a whole week of slots.
- `appointments.expire_slot_holds` (Celery beat, every ≤15 min) sweeps lapsed
  holds with `skip_locked`, so two workers cannot double-sweep and a hold always
  frees its slot on schedule rather than on the next booking attempt.
- `AvailabilityRule`/`AvailabilityException` now consult live appointments: a
  `BLOCKED` window may not be created over an active booking
  (`409 slot_occupied`), and `/availability/slots` + `/availability/dates`
  subtract real busy spans. Both are `AllowAny` *and* unauthenticated — a
  client browses slots before it has a session, and a token it may hold must not
  change the answer.
- Django admin registration for appointments: notes are the only editable field,
  the status-history inline is entirely read-only, nothing can be added or hard
  deleted, and every save is audit-logged.
- Phase 5 tests: the state machine's legal and illegal transitions, the full
  customer lifecycle (hold, idempotent replay, cancel, reschedule, expiry),
  ownership 404s, the admin filters/actions/notes-PATCH, the cancellation
  policy, the hold cap, live availability, BLOCKED-over-booking, and a
  **threaded two-connection double-booking test** against PostgreSQL that
  asserts exactly one hold survives and the loser is a 409.

## What Phase 6 has added on top of Phase 5

- `PaymentOrder`, `Payment`, `Refund`, `PaymentEvent` (`apps/payments`).
  `gateway_order_id` and `gateway_payment_id` are globally unique (these rows
  are reached from an unauthenticated webhook that has no tenant context, so
  the lookup cannot be tenant-scoped), and `PaymentEvent` is unique on
  `(gateway, event_id)` — that constraint *is* the replay defence, not an
  application check that a race could slip past.
- `apps/payments/state.py`: the payment transition table, separate from the
  appointment one. `paid_at` is stamped only by the transition into `SUCCESS`,
  so a captured payment and a paid booking can never disagree about when the
  money landed.
- `apps/payments/gateways/`: the `PaymentGateway` ABC, `RazorpayGateway` (D1)
  and a `CashfreeGateway` that raises from every method. The stub exists to
  prove the seam is not shaped around one vendor — and `factory.py` refuses to
  build *any* gateway whose name it does not recognise, so a typo in
  `DJANGO_PAYMENT_GATEWAY` is a startup error rather than a surprise on the
  first real booking.
- `POST /api/v1/payments/create-order` creates the gateway order. The amount is
  recomputed from `Service.price_amount`; a client that sends its own amount
  and gets a mismatch is told so (`409 amount_mismatch`) rather than quietly
  charged the number it asked for. The key secret and webhook secret never
  leave the server — only the publishable key id is returned.
- `POST /api/v1/payments/webhook` is `AllowAny` **and** unauthenticated: its
  credential is an HMAC over the **raw** `request.body`, verified
  constant-time *before* the payload is parsed, so an unsigned delivery leaves
  no `PaymentEvent` row at all. Every processed delivery answers 200 —
  matched, duplicate, unmatched or unhandled — because a non-2xx only earns a
  retry of an outcome that will not change. Only a bad signature is a 400. A
  capture is applied only when the payload's mode matches the order's, so a
  `test` event can never confirm a `live` booking.
- There is no route that accepts a status, an amount or a gateway payment id
  from a client. `GET /api/v1/payments/{id}/status` *reads* the gateway and
  reconciles (the fallback for a delivery that never arrived), and
  `GET /api/v1/admin/payment-events` is the audit trail for "why did this
  booking not confirm". A Phase 6 test enumerates the URLconf to assert this
  rather than trusting the prose.
- `payments.reconcile_pending_payments` (Celery beat, hourly) is the backstop
  for a webhook the gateway could not deliver. It only ever *downgrades* —
  an order the gateway no longer considers payable becomes `FAILED` — and
  confirms a capture only when `fetch_order` says paid **and** a captured
  payment can be read back. An order that reads paid with no payment id behind
  it is logged and left alone: that combination is either a gateway bug or a
  replayed order number, and neither is grounds for confirming a booking.
- Refunds are manual by decision (D2) and deliberately two-step:
  `POST /api/v1/admin/payments/{id}/refund` records a `PENDING_ACTION` `Refund`
  and moves nothing, then the lawyer issues it in the Razorpay dashboard and
  `POST /api/v1/admin/refunds/{id}/settle` records that. One click here would
  create a liability nobody agreed to. Outstanding refunds (pending **and**
  settled) are counted against the captured amount, so a replayed request
  cannot stack past what was actually charged, and a *partial* settlement
  leaves the payment `SUCCESS` with the balance still visible.
- The Django admin for all four payment models is read-only, **including
  deletion**. Overriding only `has_change_permission` still leaves Django
  serving the delete confirmation page, and deleting a payment destroys the
  evidence reconciliation later looks for — so `has_add_permission`,
  `has_change_permission` and `has_delete_permission` are all False.
- Phase 6 tests: signature valid/invalid/absent, webhook replay collapsing to a
  single transition, a client-asserted "paid" having no effect, mode isolation,
  the illegal-transition table, hold expiry landing on `EXPIRED` not `FAILED`,
  status-poll recovery of a missed webhook (and its refusal to invent a
  success without a payment id), reconciliation in every direction including a
  gateway outage, the refund two-step and its amount guards, and the
  route/serializer enumeration that proves no client-write surface exists.
