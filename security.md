# Security, Performance & Optimization Test Plan

Covers [`prd.md`](./prd.md) v1.0, [`backend-plan.md`](./backend-plan.md), [`frontend-plan.md`](./frontend-plan.md)
Scope: Django 5 + DRF + PostgreSQL + Celery/Redis backend, Next.js 15 frontend, Razorpay payment path.

> **Companion documents**
> - [`prd.md`](./prd.md) — requirements; §33 is the requirement traceability matrix, which points back here
> - [`backend-plan.md`](./backend-plan.md) — §4 API surface, §5 double-booking, §6 payments
> - [`frontend-plan.md`](./frontend-plan.md) — §3 API client, §4 booking wizard, §11 checklist
>
> Part A maps to backend phases in `backend-plan.md` §1 and frontend phases in `frontend-plan.md` §11.
> Section numbers (`§A4`, `§B2`, …) are referenced from all three documents — keep them stable,
> and run `python3 scripts/check_docs.py` to prove it.

Three parts:
- **Part A — Security** (the bulk; this file's namesake)
- **Part B — Performance**
- **Part C — Optimization verification** (prove each optimization actually works)

## 0. Traceability at a glance

Which plan phase each part of this document gates:

| This doc | Gates | Backed by |
| --- | --- | --- |
| §A1 SAST / supply chain | B Phase 0 | `pyproject.toml` ruff/mypy config, pinned deps |
| §A2 admin auth | B Phase 1 | `SIMPLE_JWT` rotation, `PASSWORD_HASHERS` Argon2id |
| §A3 client OTP | B Phase 4 | throttle scopes `otp_request` / `otp_verify` |
| §A4 authz / tenant isolation | B Phases 1–10 | `TenantMiddleware`, `TenantScopedQuerySet` |
| §A5 payments & webhooks | **B Phase 6 — done** | `PaymentGateway` ABC, `PaymentEvent` dedupe |
| §A6 input validation & injection | B Phases 2–9 | DRF serializers, no raw SQL |
| §A7 rate limiting | B Phase 10 (hold cap shipped in Phase 5) | `DEFAULT_THROTTLE_RATES` scopes, `MAX_ACTIVE_HOLDS_PER_CUSTOMER` |
| §A8 business-logic abuse / double-booking | **B Phase 5 — done** | PG `EXCLUDE` constraint, slot holds, state machine |
| §A9 data protection & privacy | B Phases 1, 7, 10 | structlog config, storage backends |
| §A10 transport / headers / infra | B Phase 10 | `SECURE_*` settings, nginx/Caddy |
| §A11 frontend security | **F Phases 0–3** | `next.config.ts` headers, HttpOnly cookies, no `dangerouslySetInnerHTML` |
| §A12 DAST & manual pen pass | B + F Phase 9 | staging, ZAP |
| §B performance | B Phases 3, 9; F Phase 8 | indexes, pagination, RSC |
| §C optimization verification | all | before/after artifacts per PR |

---

## 1. Severity & release gates

| Severity | Definition | Gate |
| --- | --- | --- |
| **S0 Critical** | Data breach, auth bypass, payment spoofing, cross-tenant access | Blocks release. No exceptions. |
| **S1 High** | Privilege escalation, IDOR on PII, stored XSS, missing signature check | Blocks release |
| **S2 Medium** | Rate-limit gaps, info disclosure, missing security header, weak config | Fix before GA, or logged with owner + date |
| **S3 Low** | Defense-in-depth gaps, cosmetic hardening | Backlog |

**Release gate:** zero S0/S1, no open S2 older than 7 days, all Part A automated suites green in CI, Lighthouse ≥ 90 on public + booking pages, p95 API latency within the Part B targets.

This gate is applied at the end of [`backend-plan.md`](./backend-plan.md) Phase 10 and
[`frontend-plan.md`](./frontend-plan.md) Phase 9, and is the pass/fail criterion for the
end-to-end flow in [`prd.md`](./prd.md) §31.

---

## 2. Tooling

| Layer | Tool | Where |
| --- | --- | --- |
| Python SAST | `bandit` | CI + pre-commit |
| Semgrep rules (security, django, owasp) | `semgrep` | CI |
| Dependency CVEs | `pip-audit`, `npm audit`, `osv-scanner` | CI, daily schedule |
| Secret scanning | `gitleaks` / `trufflehog` | CI + pre-commit |
| Container scanning | `trivy image` | CI on built image |
| IaC scanning | `checkov` / `tfsec` | CI |
| SAST-secrets in app | env assertions in settings tests | pytest |
| API DAST | OWASP ZAP baseline + active scan | Staging, nightly |
| DAST browser | Playwright + `zap` against staging | Nightly |
| a11y | `@axe-core/playwright`, Lighthouse | CI + manual |
| Load | `k6` (API), `Locust` (bursty real-world) | Pre-release + staging |
| DB query perf | `django-debug-toolbar`, `nplusone`, `EXPLAIN (ANALYZE, BUFFERS)` | Dev + CI perf test |
| Frontend bundle | `lighthouse-ci`, `@next/bundle-analyzer`, `bundlesize` | CI |
| Runtime | Sentry (backend + frontend), structured logs, `pg_stat_statements` | Prod |
| Headers/TLS | `testssl.sh`, `securityheaders.com` | Pre-launch |

Threat-model note: treat the **payment webhook** and the **admin console** as the two highest-value attack surfaces, and the client portal as the highest-value IDOR surface.

---

# Part A — Security

Each section names the plan phase it gates. `B` = [`backend-plan.md`](./backend-plan.md), `F` = [`frontend-plan.md`](./frontend-plan.md).

## A1. Automated static analysis & supply chain

> Gates B Phase 0 and F Phase 0. Ruff and mypy-strict are already configured in `backend/pyproject.toml`.

- [ ] `bandit -r apps common -lll` clean; no `assert` used for authz, no `shell=True`, no `pickle`, no `eval`
- [ ] `semgrep --config p/django` and `--config p/owasp-top-ten` run in CI, findings triaged
- [ ] `pip-audit` and `npm audit` clean, or documented exceptions with expiry
- [ ] `gitleaks` on full history — **no secrets in git**, ever (DB passwords, Razorpay key secret, JWT signing key, SMS creds)
- [ ] `trivy image` on the built backend image — no HIGH/CRITICAL
- [ ] Django `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` all fail-closed if env var missing
- [ ] `DEBUG=False` in production settings (test that asserts it)
- [ ] Dependency pinning with a lockfile; no unpinned `latest` in CI
- [ ] Signed container images / verified build provenance (nice-to-have)

## A2. Authentication — admin

- [ ] Passwords hashed with **Argon2id** (`PASSWORD_HASHERS` test asserts Argon2 is first)
- [ ] Password policy: min length 10, checked against a breach list, strength meter in UI
- [ ] Login throttled per IP **and** per email (5 attempts / 15 min); lockout returns a generic message
- [ ] Login error message does not reveal whether the email exists
- [ ] JWT access token TTL ≤ 15 min, refresh ≤ 7 days, refresh rotation enabled
- [ ] Refresh-token reuse detection invalidates the token family
- [ ] Logout invalidates the refresh token server-side
- [ ] Password reset flow: short-lived signed token, single use, invalidated after use
- [ ] No user enumeration via `/auth/admin/refresh`, `/admin/*`
- [ ] CSRF: cookie-based sessions where used; `CSRF_TRUSTED_ORIGINS` set explicitly
- [ ] Session/JWT cookies: `HttpOnly`, `Secure`, `SameSite=Lax/Strict`, correct `Path`

## A3. Authentication — client OTP (phone)

- [x] OTP codes **hashed at rest** (never plaintext in DB) — verified by inspecting a test DB
- [x] OTP expires after 5 minutes; expired codes rejected
- [x] Max 5 verification attempts per code → code invalidated
- [x] Rate limit: ≤ 3 sends/15 min per number, ≤ 10/hour per number, ≤ 20/hour per IP
- [x] Spend limits survive restart and are enforced in Redis with a DB fallback *(Phase 4 counts recent `PhoneOtp` rows directly in Postgres — same windows, durable across restarts by construction, and verifiable from the DB)*
- [x] Response for existing vs non-existing numbers is **identical** (no enumeration)
- [ ] Rate-limit headers returned; behaviour under burst load tested *(open: DRF throttles set no `Retry-After`/`RateLimit-*` headers yet; add burst-load coverage with the Phase 5 load gates)*
- [x] Phone numbers normalised (E.164) before lookup, so `+91…`, `91…`, `0…` cannot create duplicate customers
- [x] OTP never appears in logs, Sentry breadcrumbs, or error reports
- [x] Client token scope is strictly `customer`; an admin token cannot be used on `/me/*` and vice versa *(the polymorphic `GET /auth/me` serves whichever profile the token's scope allows — never cross; customer tokens are rejected outright on `/admin/*` by `AdminJWTAuthentication`)*

## A4. Authorization & tenant isolation (highest-risk area)

> Gates B Phases 1–10 (every phase adds endpoints). Implements PRD §21, §23, §32.
> Mechanism under test: `TenantMiddleware` + `TenantScopedQuerySet` (backend-plan.md §2/§8).

Backend must enforce ownership; the frontend guards in [`frontend-plan.md`](./frontend-plan.md) §3 are UX only.

- [ ] Every `/me/*` endpoint resolves the object through the authenticated customer — no raw `id` lookup
- [ ] **IDOR test:** customer A authenticated, requests customer B's appointment, payment, and profile → `404` (not `403`, to avoid confirming existence)
- [ ] Admin endpoints reject a non-admin token → `403`
- [ ] Every viewset filters by `tenant_id` from the token, never from the request body or query string
- [ ] Automated test per viewset: authenticated user from tenant B accessing tenant A's object returns 404 (add to CI as a required test, per [`backend-plan.md`](./backend-plan.md) §12 risk table)
- [ ] Mass-assignment: `tenant_id`, `role`, `status`, `price_amount` cannot be set by a client
- [ ] Object-level permission classes cover every non-public endpoint (`DEFAULT_PERMISSION_CLASSES` = `IsAuthenticated`)
- [ ] Public endpoints expose only whitelisted serializer fields — no `phone`/`email` of the provider or internal notes leak
- [ ] No debug/internal endpoints exposed in production (`/__debug__`, `/admin/` Django admin restricted or disabled, `/api/docs` in non-prod only)

## A5. Payments & webhooks (S0 surface)

> Gates B Phase 6. Implements PRD §11, §12. Mechanism under test: `PaymentGateway` ABC,
> `PaymentEvent` dedupe, `select_for_update` transitions (backend-plan.md §6).
> **Status: B Phase 6 — done.** The "one email" half of the replay item still
> waits on Phase 7 (notifications); everything else is asserted by the suite.

- [x] Webhook endpoint rejects an unsigned payload → `400`, nothing changes in DB
- [x] Signature verified with **constant-time** comparison against the raw body
- [x] Webhook parses the **raw** body — no JSON reserialization before verification (test with reordered keys + whitespace to prove it)
- [x] Amount is recomputed server-side from `Service`; a client-sent amount of ₹1 for a ₹500 service is rejected
- [x] No endpoint exists that lets a client mark a payment successful — enumerate all routes in a test and assert none accept a client-asserted status
- [x] Webhook replay: the same `event_id` delivered 3× results in exactly one transition ~~and one email~~ — the single-transition half is asserted; "one email" is Phase 7
- [x] Unknown/unmatched `gateway_order_id` → logged, no state change, `200` returned
- [x] Late webhook for a cancelled/expired appointment does not resurrect it to `CONFIRMED`
- [x] Refund endpoint is admin-only, amount ≤ captured amount, cannot be replayed
- [x] `Payment`/`PaymentOrder` gateway ids are uniquely constrained — duplicate insert fails
- [x] Reconciliation task cannot flip a `FAILED` payment to `SUCCESS` without a gateway truth
- [x] Test-mode and live-mode keys never mixed; a test-mode order cannot confirm a live booking
- [x] Payment amounts stored as `Decimal` — no float rounding drift (test ₹0.01 × N)
- [x] Gateway API keys in env/secret manager only; public key in `NEXT_PUBLIC_*` is the publishable key
- [x] Test doubles are environment-gated — production refuses to start with `PAYMENT_GATEWAY=stub`

Verified by `backend/tests/integration/test_payments.py` (webhook, replay, mode
isolation, reconcile, refunds, route enumeration, admin lock-down),
`backend/tests/unit/test_payment_gateways.py` (factory refusals, HMAC over
exact bytes, paise rounding) and `test_duplicate_gateway_order_id_cannot_be_inserted`.

## A6. Input validation & injection

- [ ] Every write endpoint has a DRF serializer; no `request.data` passed straight to a model
- [ ] Zod on the frontend is convenience only — the same tests re-run server-side
- [ ] Strict: unknown fields rejected (`extra_kwargs`/serializer strictness), unexpected types → `400`
- [ ] **SQL injection:** `RawSQL`/`extra()`/`cursor()` use is banned unless parameterized; semgrep rule `python.django.security.audit.raw-sql` enabled; fuzz search/filter params
- [ ] **XSS:** no `dangerouslySetInnerHTML` in the frontend (grep in CI); notification text, client names, notes, and FAQ rendered as text
- [ ] Stored XSS test: create a service/notes/profile containing `<script>`, `<img onerror>`, `{{7*7}}` → renders inert, and admin pages are also safe
- [ ] Notes/free-text length caps enforced server-side; content-type sniffing prevented
- [ ] **SSRF:** no user-controlled URL fetching anywhere; if provider logo URLs are supported later, add an allowlist + block private ranges
- [ ] **File upload:** if attachments arrive later — content-type sniffing, size caps, storage outside webroot, filename sanitization, AV scan
- [ ] **Path traversal** and **open redirect** on `next`, `returnTo`, and the login `redirect` param → allowlist of internal paths only
- [ ] Integer/array params bounded (page size ≤ 100, ids, durations, prices) to prevent DoS and slow queries
- [ ] Regex DoS check on any user-supplied search pattern

## A7. Rate limiting & abuse

- [ ] DRF throttle scopes: `otp_request`, `otp_verify`, `booking_create`, `login`, `webhook`, global anonymous
- [x] Per-user **and** per-IP throttles; authenticated users throttled by customer id
- [x] Slot-hold abuse: repeated `POST /appointments` without paying is capped (e.g. 5 active holds per customer) so inventory can't be griefed — `MAX_ACTIVE_HOLDS_PER_CUSTOMER`, `409 hold_limit_reached`; the cap counts unpaid `PENDING_PAYMENT` holds only, so confirmed appointments are never blocked
- [x] Calendar slot endpoint throttled to prevent scraping of the full schedule
- [ ] 429 responses include `Retry-After`; frontend degrades gracefully
- [ ] Verified under burst load with k6 (Part B) that throttles hold and don't leak memory
- [ ] No user-controlled amplification: report/export endpoints are paginated and time-bounded

## A8. Business-logic abuse (the ones generic scanners miss)

> Gates B Phases 2–5 and 9. Implements PRD §7 (critical) and §8.
> The concurrency test below is the direct verification of PRD §31's final acceptance line.

- [ ] Negative/zero price, duration `0`, or a service duration of `99999` rejected
- [x] Booking in the past rejected; beyond the booking horizon rejected; inside the lead time rejected
- [x] Slot must exactly match a server-generated slot (arbitrary times rejected) — the server re-derives the grid and uses its own duration, so a client cannot buy a different appointment than the one it asked for
- [x] Service inactive or deleted → cannot be booked
- [x] Cancellation blocked inside the policy window; refund not promised when policy says manual
- [x] Reschedule cannot be used to bypass the cancellation window — a client-side reschedule runs the same window check as a cancel (`409 cancellation_window`); admin moves are exempt by design
- [x] Completed/no-show appointments cannot be cancelled
- [x] Status transitions restricted by the state machine — a direct `PATCH status=CONFIRMED` is rejected (400; notes are the only editable field)
- [ ] Reports and balances never derivable from client-submitted values
- [x] **Double-booking invariant test (S0):** 2+ concurrent requests for the same provider+slot → exactly one `201`, all others `409`, and exactly one appointment row. Run against PostgreSQL, not SQLite. Implements the `EXCLUDE USING gist` constraint in [`backend-plan.md`](./backend-plan.md) §5 layer 2. *Two real connections, not two sequential calls: PostgreSQL can abort the loser either with an `IntegrityError` or with a deadlock/serialisation failure while ordering the two exclusion-index probes, and both are translated into the same `409` rather than a 500.*
- [x] Hold-expiry sweep frees abandoned slots; no permanent inventory leak
- [x] Invariant check job in CI: no two overlapping non-cancelled appointments per provider, asserted directly against the DB — *enforced by the exclusion constraint itself, and asserted by the threaded test above*

## A9. Data protection & privacy

- [ ] PII inventory: phone, email, name, notes, address, payment ids — where each is stored, logged, and cached
- [ ] **No PII in logs** — test: make a full booking, then grep all app logs, Celery logs, Sentry, and Redis for the phone/email → zero matches
- [ ] Debug toolbar / SQL logging with parameters disabled in production
- [ ] Redis requires auth, is not publicly reachable, and is not used to store PII beyond short-lived session/cache data
- [ ] Database requires TLS, least-privilege app user (no `SUPERUSER`, no DDL at runtime), and no default credentials
- [ ] Backups encrypted, access-logged, retention policy defined; **restore drill performed** at least once and verified
- [ ] Data deletion/export path exists for a customer's phone, email, and notes (deletion must respect financial record-retention obligations — get the retention window confirmed in `backend-plan.md` §11 Q8)
- [ ] GDPR/consent note captured at booking if the client operates in the EU; cookie/consent banner if analytics is added
- [ ] Provider/secret key rotation procedure documented and tested once

## A10. Transport, headers, and infrastructure

- [ ] TLS 1.2+ enforced, HSTS enabled with a sane `max-age`, HTTP → HTTPS redirect
- [ ] `SSL Labs` grade A (or A-) for the API and web hosts
- [ ] Security headers on every response:
      `Content-Security-Policy` (no `unsafe-inline` in prod; Razorpay domains allowlisted),
      `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` / `frame-ancestors 'none'`,
      `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` (deny camera/mic/geolocation)
- [ ] Verified by `testssl.sh` + ZAP that headers are present on **API responses too**, not just HTML
- [ ] CORS allowlist is the exact frontend origin(s); `Access-Control-Allow-Credentials` never paired with `*`
- [ ] API never cached at a CDN/proxy in a way that leaks one user's response to another (`Cache-Control: private, no-store` on `/me/*` and `/admin/*`)
- [ ] Nginx/Caddy: no directory listing, no `.env`/`.git`/source maps exposed, request body size capped
- [ ] Admin console reachable only over VPN/allowlist/IP-restricted if possible; Django admin disabled in prod
- [ ] Error responses never leak stack traces, SQL, or settings (`DEBUG=False`; DRF handler returns a stable shape)
- [ ] Container runs non-root, read-only filesystem where possible, no Docker socket, no cloud metadata reachable (IMDSv2 enforced)
- [ ] Secrets in a secret manager, not baked into images; `.env` gitignored
- [ ] Dependency/runtime patching cadence and an incident response + backup-restore runbook exist

## A11. Frontend-specific security

> Gates [`frontend-plan.md`](./frontend-plan.md) Phases 0–3, especially §9 hardening and §11
> Phase 0 (`next.config.ts` headers). Token strategy per frontend-plan.md §3.

- [ ] Tokens in HttpOnly cookies only — grep confirms **no** `localStorage`/`sessionStorage` use for tokens (the booking draft is fine)
- [ ] No secret in any `NEXT_PUBLIC_*` variable
- [ ] `next.config.ts` headers applied to all routes incl. API routes; CSP enforced in report-only mode first, then blocking
- [ ] Client-side route guards are bypassed harmlessly — verified by hitting `/admin/*` unauthenticated and getting a clean 401/redirect, never data
- [ ] XSS sinks: `dangerouslySetInnerHTML`, `href={userValue}`, `style={userValue}` — reviewed and absent
- [ ] `target="_blank"` links carry `rel="noopener noreferrer"`
- [ ] React escapes by default — no `eval`, no `Function()`, no template HTML injection
- [ ] Payment SDK loaded only on the payment step, from the allowlisted CDN
- [ ] Service worker / caching (if ever added) must not cache `/me/*` or `/admin/*`

## A12. DAST & manual penetration pass (staging)

- [ ] `zap-baseline.py` against the web and API hosts — zero HIGH+
- [ ] ZAP active scan with a reduced-strength profile, in a staging environment with test data only
- [ ] OWASP ZAP authenticated scan (logged in as admin **and** as a client)
- [ ] Manual checks: IDOR sweep across every resource id; JWT tampering/algorithm confusion (`alg: none` rejected — test it); token expiry; privilege escalation by editing claims; replay of a valid booking request with a modified body; webhook replay; mass assignment on every PATCH endpoint
- [ ] Check for any endpoint or GraphQL/DRF browsable API leaking the schema in prod (`Accept: text/html` on `/api/v1/` → no browsable UI)

---

# Part B — Performance

> Gates B Phases 3 and 9 (slot engine, reports) and F Phase 8 (hardening/budgets).
> Targets originate in PRD §29 and are enforced as CI budgets in F §11.

Targets from PRD §29, restated as measurable SLOs.

| Metric | Target |
| --- | --- |
| Public page LCP | < 2.5 s (mobile, 4G) |
| Booking wizard interactive | < 3 s, JS ≤ 150 KB gz |
| `GET /availability/slots` | p95 < 200 ms, p99 < 400 ms |
| `GET /services` | p95 < 150 ms |
| `POST /appointments` | p95 < 500 ms (includes hold + order create) |
| Admin list endpoints (paginated) | p95 < 500 ms |
| Report endpoints | p95 < 800 ms for a 12-month range |
| Webhook processing | p95 < 300 ms, async work < 1 s |
| Error rate | < 0.1% |
| Uptime | 99.5% |

## B1. Environments & data shape

- [ ] Staging sized like production (or documented delta); results annotated with the delta
- [ ] Realistic seed: 5 services, 3 availability rules, 5,000 customers, 20,000 appointments over 12 months, 20,000 payments, 50,000 audit rows, 100,000 notifications
- [ ] Audit log grows the fastest — verify it doesn't degrade every query

## B2. API load tests (k6)

- [ ] **Read baseline:** 50 VU, 10 min, `GET /services`, `GET /availability/slots`, `GET /me/appointments` — p95 within target, no 5xx
- [ ] **Booking spike:** 200 VU hammering `POST /appointments` for the same provider/slot → expect 1 `201`, rest `409`, zero `500`, DB error rate ~0 (proves the exclusion constraint degrades gracefully)
- [ ] **Calendar crawl:** a "bot" walks 365 days of `GET /availability/dates` → verify throttling, and that it cannot enumerate the full schedule quickly
- [ ] **Admin browse:** 20 VU paged through appointments/clients/payments with filters → no N+1 regression under real traffic
- [ ] **Report load:** 5 VU on date-range reports, 12-month span
- [ ] **Webhook burst:** 500 events/min replayed, mixed valid/signed-invalid/duplicate/out-of-order → ordering holds, no lost transitions, no duplicate emails
- [ ] **Reminder burst:** 10,000 due reminders in one tick → job completes within the beat interval, workers don't collide, no double-send
- [ ] **Soak:** 4 h at 60% peak, watching for connection-pool exhaustion and memory growth
- [ ] **Spike:** 5× expected peak for 60 s, then recovery — verify the system returns to baseline

## B3. Database

- [ ] `EXPLAIN (ANALYZE, BUFFERS)` captured for every endpoint in the matrix below and stored as a baseline artifact
- [ ] Key queries confirmed to use the intended index (no seq scans on `appointments`/`payments` at realistic volume):
      slot availability for a date, appointments filtered by date+status, customer search, revenue aggregation, reminder sweep, audit log page
- [ ] Every list endpoint verified to use server-side pagination — no endpoint loads the full table
- [ ] `pg_stat_statements` reviewed: top 20 queries by total time, no unplanned N+1 (query count per request is constant as row counts grow)
- [ ] `nplusone` detector run across the test suite → zero
- [ ] Index-only scans where expected; unused indexes identified and dropped
- [ ] Connection pool sized correctly (PgBouncer or `CONN_MAX_AGE`) — no "too many connections" under peak
- [ ] Slow-query log threshold set (e.g. 500 ms) with alerting
- [ ] Autovacuum/analyze healthy on the high-churn tables (`appointments`, `payments`, `audit_logs`, `notifications`)
- [ ] Count-estimates sane for the exclusion-constraint check (bloat from churn measured at 10k+ inserts)

## B4. Cache & background jobs

- [ ] Redis hit ratio for slot caching recorded; invalidation on rule/appointment change verified (no stale slots served past `staleTime`)
- [ ] Slot cache doesn't mask a booking — verified by writing, then bypassing the cache, then re-testing
- [ ] Celery: task p95 duration, queue depth, worker concurrency, and `acks_late` behaviour under worker kill
- [ ] Beat scheduler doesn't run duplicate sweeps (single beat instance enforced, or DB-backed lock)
- [ ] Email send failures retried then dead-lettered; a failed provider doesn't block the queue
- [ ] Memory of workers flat over the soak test (no unbounded task payload retention)

## B5. Frontend performance

- [ ] `lighthouse-ci` in CI with a ≥ 90 budget on landing, service list, and booking step 1
- [ ] `@next/bundle-analyzer` — no single client chunk > 150 KB gz; the payment SDK and calendar are dynamically imported and absent from the public bundle
- [ ] No waterfall: booking step 1's service list comes from a Server Component, not a client-side fetch
- [ ] Images via `next/image` with correct `sizes`; LCP element is the hero/logo, preloaded
- [ ] Route-level code splitting verified — admin JS never ships to public pages
- [ ] CLS < 0.1 (skeletons match final layout)
- [ ] INP < 200 ms on the slot grid under 200 slots
- [ ] Third-party scripts limited to the payment step, loaded with `next/script` after interaction
- [ ] `Cache-Control` correct: `no-store` on `/me/*` and `/admin/*`, long immutable caching on hashed static assets

---

# Part C — Optimization verification

> Gates every phase in both plans. The rule: no optimization merges without a before/after
> artifact attached to the PR, and no optimization may weaken a §A4 or §A8 guarantee.

Each optimization only ships with a before/after number. Record the baseline before changing anything.

| Optimization | How to prove it works | Pass criteria |
| --- | --- | --- |
| Slot cache in Redis | Hit `GET /availability/slots` 1000×, compare p95 cached vs cache-disabled | p95 improves ≥ 50% and correctness tests still pass |
| Composite indexes | `EXPLAIN` before/after on the 6 key queries | Seq scan → index scan; target query time ≥ 3× faster |
| `select_related`/`prefetch_related` | `django-debug-toolbar` query count per request | Constant query count as rows grow; N+1 gone |
| Server-side pagination | Request 10k appointments, measure response time + payload size | Constant time/size vs page size; < 100 KB payload |
| `only()`/`defer()` on heavy serializer fields | Compare query cost and payload | Measurable drop, no `DeferredAttribute` bugs |
| Aggregation pushdown (`annotate`/`Sum` in SQL) | Compare ORM aggregate vs Python-side sum over 20k rows | 10×+ faster on the 12-month report |
| RSC for public pages | Network tab — HTML arrives with content, no client refetch | No `/api/v1` call needed for first paint |
| Code splitting (payment SDK, calendar) | Bundle analyzer | Admin + payment JS absent from public chunks |
| Route prefetch / link prefetch | Navigation timing between booking steps | Step transition < 300 ms perceived |
| Skeletons instead of spinners | Lighthouse CLS | CLS < 0.1 |
| Index-only query for reminder sweep | `EXPLAIN` | "Index Only Scan" used |
| Audit log sampled or async-written | Request latency with/without audit sync write | Write not on the critical path |
| `select_for_update(skip_locked=True)` in reminders | Two workers, same tick | No duplicate sends, no lock contention |
| `EXCLUDE` constraint vs advisory lock | Booking throughput benchmark | p95 within the Part B targets; keep whichever is faster and correct |

Guardrails:
- Every perf claim is attached to a k6 run ID and an `EXPLAIN` artifact in the PR description.
- A performance regression > 20% on any target blocks merge (run k6 nightly against `main`).
- Optimization is never a reason to weaken correctness — the double-booking and ownership tests are non-negotiable and run in the same CI job.

---

## D. CI pipeline (target layout)

```
lint:       eslint, tsc --noEmit, ruff, bandit
secrets:    gitleaks, env assertion tests
deps:       pip-audit, npm audit, osv-scanner, trivy image
tests:      pytest (unit + integration + concurrency), vitest, playwright
a11y:       axe on key routes
quality:    django migrations --check, mypy
perf:       k6 smoke (read + booking-spike) against a disposable service
budgets:    lighthouse-ci assertions, bundlesize
```

Nightly/staging only: full k6 matrix, ZAP active scan, soak test, DB `EXPLAIN` baseline diff, audit-log growth check.

## E. Pre-launch checklist (final pass)

- [ ] Zero S0/S1 findings
- [ ] `testssl.sh` A- or better on both hosts
- [ ] Security headers verified on API and web, including `no-store` on authenticated routes
- [ ] Backup taken **and restored** successfully into a clean instance
- [ ] Secrets rotated from any dev value; production credentials confirmed unique
- [ ] Django admin disabled; debug endpoints off; no sample/test data in prod
- [ ] Error monitoring live and PII-free
- [ ] Rate limits tuned against real burst behaviour
- [ ] Full PRD §31 flow executed in staging, including the double-booking attempt
- [ ] Performance targets met at expected peak, with artifacts attached
- [ ] Incident + rollback runbook written and read by the team
- [ ] Pen-test or second-pair-of-eyes review of payments + authorization completed

## F. Ongoing cadence

| Cadence | Activity |
| --- | --- |
| Per PR | Lint, SAST, secrets, unit/integration, a11y, Lighthouse, k6 smoke |
| Nightly | Full k6 matrix, ZAP scan, dependency re-check, DB plan diff |
| Monthly | Review S2 backlog, rotate secrets, review access & audit logs, dependency updates |
| Quarterly | Restore drill, load test at higher ceiling, threat-model review, penetration retest |
| On every release | Full Part E gate, signed off by two people |

## G. Bug report template

```
Severity: S0 / S1 / S2 / S3
Component: backend / frontend / infra / payments / auth
Endpoint or route:
Preconditions (tenant, role, data state):
Steps to reproduce:
Expected:
Actual:
Evidence (test ID, request/response with secrets redacted, log excerpt, screenshot, k6 or EXPLAIN output)
Impact / blast radius:
Workaround:
```

---

## H. Open questions for security review

Consolidated with the product questions in [`backend-plan.md`](./backend-plan.md) §11 and
[`frontend-plan.md`](./frontend-plan.md) §13. These are compliance decisions, not tests — they
change what §A9 and §A10 must verify, so answer them before the security review starts.

1. Are we subject to DPDP Act (India), GDPR, or sector-specific retention rules? This drives §A9.
2. Must client phone/email be encrypted at rest beyond disk/database encryption?
3. Is the admin console to be IP/VPN-restricted, or internet-exposed behind auth?
4. Payment data storage — do we need PCI-relevant scoping (tokenised references only vs storing more)?
5. Do we need a formal pen test before launch, and by whom?
6. Audit-log retention and immutability requirement? (Bears on PRD §22 / backend-plan.md §1 audit app.)
7. Data residency constraint on where backups and logs are stored?

---

## I. Related documents

- [`prd.md`](./prd.md) — requirements source of truth; §33 traceability matrix points into this file
- [`backend-plan.md`](./backend-plan.md) — §4 API surface, §5 double-booking, §6 payments, §8 security settings
- [`frontend-plan.md`](./frontend-plan.md) — §3 auth/token strategy, §4 booking wizard, §9 hardening, §11 checklist
