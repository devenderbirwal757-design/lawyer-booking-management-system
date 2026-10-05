# Frontend Implementation Plan — Lawyer Booking & Management System

Derived from [`prd.md`](./prd.md) v1.0 + [`backend-plan.md`](./backend-plan.md)
Stack: **Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui + TanStack Query + RHF + Zod**

> **Companion documents**
> - [`prd.md`](./prd.md) — requirements source of truth, §33 traceability matrix
> - [`backend-plan.md`](./backend-plan.md) — §4 is the API contract this app consumes
> - [`security.md`](./security.md) — §A11 frontend security, §A6 XSS, §B5 bundle/perf budgets
>
> Backend phases gate frontend phases: this document's §11 checklist cites the backend phase
> that must land first for each step. Section numbers are referenced from [`prd.md`](./prd.md)
> §33 — keep them stable, and run `python3 scripts/check_docs.py` to prove it.

---

## 0. Scope

Two distinct surfaces sharing one app:

| Surface | Route group | Audience | Priority |
| --- | --- | --- | --- |
| Public / booking | `(public)` | Prospects | MVP |
| Client portal | `(customer)` | Authed clients (phone OTP) | MVP |
| Admin console | `admin/` | The lawyer | MVP |

---

## 1. Guiding decisions

| PRD requirement | Frontend decision |
| --- | --- |
| "Frontend availability alone is not sufficient" | The UI never decides availability. It renders what `GET /availability/slots` returns, and always re-submits through the server. Slot lists are refetched on date change and after any booking attempt. |
| Booking in as few steps as practical | One-page 4-step wizard (`Service → Date & Time → Details → Payment`) with a single URL, `?service=&date=` deep-linkable, no hard redirects between steps. |
| "The frontend must never be trusted to declare a payment successful" | No client code writes a payment status. The success screen waits for `GET /appointments/{id}` to report `CONFIRMED`; Razorpay's callback only triggers a **re-fetch**, never a state mutation. |
| Mobile-first, responsive | Tailwind mobile-first, breakpoints at `sm/md/lg`. Booking flow designed at 360px first, verified at 390/768/1280. |
| Accessible | shadcn/ui primitives + Radix; keyboard-navigable date/slot grids, `aria-live` for status, visible focus rings, contrast ≥ 4.5:1. |
| Fast | Server Components for public pages, TanStack Query only where interactivity is needed, no heavy client bundle on the landing page. |
| Versioned API from day one | Single `API_URL` env var ending in `/api/v1`. All calls go through one typed fetch client. |
| Admin is desktop-first | Dense tables, sticky filters, keyboard shortcuts; degrades to cards on mobile. |

---

## 2. Repo layout

```
frontend/
├── app/
│   ├── (public)/
│   │   ├── layout.tsx                     # public chrome: header, footer, FAQ, legal
│   │   ├── page.tsx                       # landing: profile, practice areas, services, pricing, CTA
│   │   ├── services/page.tsx
│   │   ├── services/[slug]/page.tsx
│   │   └── book/page.tsx                  # the 4-step wizard (?service=&date=&time=)
│   ├── (customer)/
│   │   ├── login/page.tsx                 # phone + OTP
│   │   ├── dashboard/page.tsx             # upcoming / past / cancelled
│   │   ├── bookings/[id]/page.tsx
│   │   └── profile/page.tsx
│   ├── admin/
│   │   ├── layout.tsx                     # sidebar, topbar, auth guard
│   │   ├── page.tsx                       # dashboard KPIs + today's list
│   │   ├── appointments/page.tsx
│   │   ├── appointments/[id]/page.tsx
│   │   ├── calendar/page.tsx              # month / week / day
│   │   ├── clients/page.tsx  +  [id]/page.tsx
│   │   ├── services/page.tsx
│   │   ├── payments/page.tsx
│   │   ├── reports/page.tsx
│   │   ├── settings/page.tsx
│   │   └── audit/page.tsx
│   ├── api/                               # next-auth style route handlers (BFF/proxy)
│   ├── error.tsx  not-found.tsx  loading.tsx
│   ├── layout.tsx  globals.css
│   └── opengraph-image.tsx
├── components/
│   ├── ui/                                # shadcn (generated)
│   ├── booking/                           # steps, date picker, slot grid, forms, payment
│   ├── admin/                             # data table, filters, KPI cards, status badge, action menu
│   └── shared/                            # logo, status badge, price, empty state, confirm dialog
├── features/                              # per-domain hooks + zod schemas + types
│   ├── auth/  services/  scheduling/  appointments/  payments/
│   ├── customers/  notifications/  reports/
├── lib/
│   ├── api/                               # client.ts, endpoints.ts, error.ts, query-keys.ts
│   ├── auth/                              # token store, session provider, route guard
│   ├── utils/  hooks/  validation/
│   └── constants/
├── stores/                                # zustand: booking draft only
├── types/                                 # generated/handwritten API types
├── tests/{unit,e2e}/                      # vitest + playwright
├── public/
├── middleware.ts                          # route protection
├── next.config.ts  tailwind.config.ts  components.json
├── .env.example
└── README.md
```

---

## 3. API client & auth

### Typed client
```ts
// lib/api/client.ts
- one fetch wrapper: baseURL, JSON, credentials: 'include', X-Request-ID
- on 401: attempt refresh once, retry original, else redirect to login
- on 409 SLOT_UNAVAILABLE: revalidate slot query, surface inline error
- parse error envelope { error: { code, message, details } } into ApiError
```
- Zod schemas in `features/*/schema.ts` validate **responses**; TS types inferred from them.
- `query-keys.ts` is the single source of truth for cache keys (`['slots', serviceId, date]`, `['admin','appointments',filters]`).

### Token strategy
- Access + refresh tokens in **HttpOnly, Secure, SameSite=Lax cookies** set by backend; the browser JS never reads them.
- Next.js `middleware.ts` handles coarse redirects (unauthenticated → `/login`).
- Server-side data fetching in RSC passes cookies through to the API for `/me/*` and `/admin/*` routes.
- Client-only queries (slot picking, mutations) use TanStack Query.

### Route guards
- `requireCustomer()` in `(customer)/layout.tsx`
- `requireAdmin()` in `admin/layout.tsx` (server-side, 401 → `/admin/login`)
- Never rely on these for security — backend enforces ownership (PRD §21); the guards are UX only.

---

## 4. Booking wizard (the critical flow)

PRD §4 flow, collapsed to 4 visible steps by moving phone verification inline with the details step.

```
1 Select service  → 2 Date & Time  → 3 Details (+ OTP)  → 4 Payment  → 5 Confirmed
```

**State**
- `useBookingStore` (zustand, persisted to `sessionStorage`): `serviceId, date, startAt, customer{name,phone,email}, notes, coupon?`
- Draft survives a refresh so a client returning from a failed payment doesn't lose the slot.
- Steps are individually validatable; a client can jump back freely, forward only when valid.

**Step 1 — Service**
- Grid of service cards: name, duration, formatted price, description.
- Query: `GET /services?status=active` (SFC prefetch, hydrated to the client query cache).
- URL sync: selecting a service rewrites to `?service=<slug>`.

**Step 2 — Date & Time**
- Horizontal 14-day date strip + full month picker, built on a date lib that handles the tenant timezone.
- Slots: `GET /availability/dates?service_id=&month=` for the month grid (days with availability get a dot).
- On date select: `GET /availability/slots?service_id=&date=YYYY-MM-DD`.
- `useQuery({ staleTime: 15_000, refetchOnWindowFocus: true })` — stale slots are the main double-booking risk in the UI.
- Slot grid: fixed-height scroll region, `role="radiogroup"`, keyboard arrow navigation, group by morning/afternoon/evening.
- **Do not assume 30-minute rows** (backend-plan.md D4 — slots are service-driven, so a 45-min service returns 45-min-spaced times). Render each start as given, and show the service duration next to the slot or in the header. No client-side slot arithmetic, no snapping to the nearest 30, no "duration" column inferred from neighbours.
- **A slot that disappears between render and click is normal, not a bug** (D5: booked times block automatically). The 409 recovery path in step 4 is the designed response — do not try to prevent it optimistically.
- "No times available" state with next-available-date suggestions instead of a dead end.

**Step 3 — Details**
- React Hook Form + Zod: name, phone (10-digit Indian), email, notes (optional, 500 char).
- **Email is optional** (backend-plan.md D3). Render it as a clearly optional field with the reason stated inline — "so we can email your confirmation and reminder" — not as a required field with an asterisk the client feels forced to satisfy. If they skip it, the wizard proceeds and step 5 says the confirmation is available in the portal.
- On submit: `POST /auth/otp/request`. Inline 6-box OTP input, `autocomplete="one-time-code"`, 5:00 countdown with resend.
- `POST /auth/otp/verify` returns the customer token; name/email from this form upsert the profile.
- Unknown client → seamless; returning client → fields prefilled from the token.

**Step 4 — Payment**
- On entry: `POST /appointments` (creates the hold) then `POST /payments/create-order`.
- Load Razorpay Checkout with the returned `order_id` + server-computed amount + public key.
- On `handler(response)`: **do not** set state from the callback. Call `GET /appointments/{id}` on a short poll (1s × 5) until `status === 'CONFIRMED'`, showing "Verifying your payment…".
- Failure/close: keep the booking in `PENDING_PAYMENT`, offer Retry (reuses the same order) and Cancel (frees the hold immediately).
- Hold countdown banner: "Your slot is reserved for 09:58" — sourced from `slot_hold_expires_at`.

**Step 5 — Confirmed**
- Booking ID, service, date/time, amount, payment status, status badge.
- "Add to calendar" (`.ics` generated client-side), download receipt, link to dashboard.

**Error handling:** inline field errors from `details`, a dismissible banner for global errors, and a 409 on the slot redirects back to step 2 with "That time was just taken — here are the closest options."

---

## 5. Client portal

- **Dashboard:** three tabs (Upcoming / Past / Cancelled) from `GET /me/appointments?status=`, cards with date, time, service, price, payment + booking badges, "View details" CTA. Nearest upcoming appointment promoted to a hero card.
- **Booking detail:** full detail per PRD §10 + status history timeline + actions (Cancel, Reschedule) shown only when the policy allows.
- **Cancel:** confirm dialog showing the honest refund outcome. With manual refunds (backend-plan.md D2) the copy must **not** promise money back automatically — it states whether the appointment is refund-eligible, and if so that the lawyer processes it separately. Requires a reason, posts, then invalidates queries.
- **Refunds:** the client's payment view shows `Refund pending` once a refund is requested and `Refunded` only after the lawyer settles it (B D2, B §6.2). Two distinct client-visible states, never conflated.
- **Reschedule:** reuse the slot picker in a modal, preview the new time, submit, refresh both appointments.
- **Profile:** name, phone (change requires re-verification), email, notification preferences.
- **Empty states** for every list; skeletons that match final layout to avoid shift.

---

## 6. Admin console

- **Layout:** collapsible sidebar, topbar with search + admin profile, responsive drawer under `lg`. Route-level `loading.tsx` for streamed content.
- **Dashboard (PRD §13):** KPI row — Today / Upcoming / Clients / Revenue — from `GET /admin/reports/dashboard`; below, today's appointments list with time, client, service, payment status.
- **Appointments (PRD §14):** server-side paginated table with filters for date, status, service, payment status, client, plus debounced name/phone search. Row actions via a dropdown: Confirm, Cancel, Complete, No-show, Reschedule — each opens a confirm dialog and optimistically updates with rollback on failure. Detail page shows status history, payment, and audit trail.
- **Calendar (PRD §16):** month / week / day toggle on `GET /admin/calendar`. Month cells show a count + a dot; day view shows a time-grid where each block is colored by service and labelled Available / Booked / Blocked. Click a free block → "Block time" (creates an exception) or "New booking".
- **Clients (PRD §15):** search + table; profile page with contact info, appointment history, payment history, and an editable notes textarea. Explicitly **no** case-management fields.
- **Services:** CRUD table + drawer form (name, description, duration, price, currency, active toggle). Warn that a price change does not alter existing bookings.
- **Payments:** table with status/gateway/date filters, detail with gateway ids, refund action.
- **Reports (PRD §20):** Today / This week / This month / Custom range selector driving appointment and revenue cards.
- **Settings:** tenant profile (name, bio, practice areas, contact, FAQ, logo), currency, timezone, reminder offsets, cancellation policy, working hours.
- **Audit log:** filterable table of admin actions with before/after diff expansion.
- Cross-cutting: URL-synced filter state so any admin view is shareable/bookmarkable; consistent empty/loading/error states.

---

## 7. Design system

- `components.json` + shadcn/ui; extend the neutral base with a single "legal/professional" accent (deep navy + warm neutral), used consistently for primary actions.
- Tokens in `globals.css` via CSS variables: color, radius, font scale, spacing; light theme only for MVP, dark mode deferred.
- Typography: one sans (Inter/Geist) with a serif accent for the lawyer's name in the public header.
- Components to build once, reuse everywhere: `StatusBadge` (appointment + payment variants), `DataTable` (sort/filter/paginate/empty/loading), `ConfirmDialog`, `Money` (currency formatting), `DateTimeRange` (tenant TZ aware), `FormField`, `EmptyState`, `Skeleton`, `ErrorBanner`, `PageHeader`.
- Responsive table pattern: table on `md+`, stacked definition cards below.
- Icons: `lucide-react` only. No icon font.

---

## 8. Performance

- Public landing + service pages: Server Components, static where possible, `generateMetadata` for SEO.
- `@tanstack/react-query` with a single `QueryClientProvider` in the root layout; sensible defaults (`staleTime: 30s`, `retry: 1`).
- `next/image` for the avatar/logo; never `<img>` raw.
- Dynamic imports for the payment SDK and the admin calendar grid — they must not inflate the public bundle.
- Target: Lighthouse ≥ 90 on public pages, LCP < 2.5s, booking wizard interactive < 150KB gzipped JS.
- Server Components for the initial admin dashboard; client components only for interactivity.
- API list endpoints are paginated server-side, so the UI never fetches full collections.

---

## 9. Security & privacy

- Tokens in HttpOnly cookies only; never `localStorage`.
- All forms validated by Zod client-side **and** re-validated server-side — the client check is UX, not security.
- `NEXT_PUBLIC_*` for the publishable gateway key only; secret keys stay in the backend.
- CSP + `X-Frame-Options` via `next.config.ts` headers; `Referrer-Policy`.
- HTML-escaped notes/labels; no `dangerouslySetInnerHTML` anywhere (including rendered notification text).
- Error boundaries with generic user-facing copy; Sentry-style reporting in prod, no PII in logs.
- Env: `.env.local` for dev, platform env vars for prod, `.env.example` documented.

---

## 10. Testing strategy

- **Vitest + Testing Library:** form validation, slot-grid selection, status badge mapping, price formatting, `api/client` error mapping, booking store transitions.
- **MSW** to mock the OpenAPI-generated endpoints — contract tests against the real schema.
- **Playwright (E2E):** the PRD §31 flow end-to-end — browse service → pick slot → OTP → pay (gateway stubbed) → confirmation → visible in admin → reminder job stubbed → mark completed.
- Plus: client cancel/reschedule, ownership check (client B cannot open client A's booking), admin filters, empty states, 409 double-booking recovery.
- **a11y:** axe checks on booking + admin dashboard; keyboard-only booking pass.
- CI: `tsc --noEmit`, ESLint, Vitest, Playwright against a stacked-up backend + seed data.

---

## 11. Implementation checklist

Status: **Phases 0–7 complete. Phase 8 complete, including the throttled-mobile Lighthouse budget.
Phase 9 is scaffolding only** — the container and monitoring artifacts exist, but nothing is
deployed. `frontend/` is the source of truth for status; checkboxes below reflect the code on
disk as of this update.

The **Needs** column names the backend phase from [`backend-plan.md`](./backend-plan.md) that
must land first — do not start a frontend phase before its backend dependency exists.
Security column points at the gating tests in [`security.md`](./security.md).

### Deviations from the original plan

The as-built tree differs from §2 in three ways, and these are now the intended layout:

- **Route groups**: booking lives in its own `(booking)/book` group, not `(public)/book`;
  the admin console is nested under `admin/(shell)/` with `admin/login` outside the shell.
- **Feature domains** are consolidated into `features/{booking,auth,portal,admin,services}`
  rather than one directory per backend resource.
- **`next-themes` is installed** even though dark mode is deferred — it is pinned to
  `forcedTheme="light"` in `app/providers.tsx`, so the dependency is inert scaffolding for
  the deferred dark-mode work, not a shipped feature.

### Known gaps carried out of Phase 8

All four Phase 8 gaps are closed: the Playwright suite exists and is green, the
frontend CI job is wired, Lighthouse tooling records a result, and the throttled-mobile
budget is met on both gating profiles. What remains are these carried in from earlier phases:

- **Mobile Lighthouse budget** — closed; both profiles gate in CI, so this cannot regress
  silently. The browser floor it was bought with (`browserslist`) is a real support decision:
  see Phase 8.
- **E2E reaches the backend through a test proxy.** `scripts/test-api-proxy.mjs` works around
  the backend having no CORS middleware and advertising no-slash service paths that DRF serves
  with a trailing slash. It is a test seam, not a production fix.
- **Payment cannot be exercised end to end.** Razorpay test credentials and the webhook secret
  are unset, so `booked payment → webhook → confirmation` stays `test.fixme()`.

> Fixed since the last audit: `axe-core` was an undeclared dependency (present in
> `node_modules`, imported by `tests/unit/a11y.test.tsx`, absent from `package.json`). It is
> now pinned at `^4.13.0` in `devDependencies` and verified to resolve from a clean
> `npm ci`, so the axe gate in Phase 8 is reproducible on CI.

### Phase 0 — Scaffold (needs: backend Phase 0)
- [x] `create-next-app` with TypeScript, Tailwind, App Router, ESLint, `src/` off (match the layout above) — S §A11
- [x] Install deps: `@tanstack/react-query`, `react-hook-form`, `@hookform/resolvers`, `zod`, `zustand`, `react-day-picker`/`date-fns`, `lucide-react`, `sonner`
- [x] `npx shadcn init` + add base components (button, input, form, dialog, select, table, tabs, badge, skeleton, toast, calendar, popover, dropdown-menu, sheet, alert)
- [x] Design tokens in `globals.css`; theme config
- [x] Folder scaffolding per §2, plus `lib/api/client.ts`, `query-keys.ts`, `error.ts`
- [x] `QueryClientProvider` + `Toaster` in root layout
- [x] ESLint/Prettier, `tsconfig` strict, husky + lint-staged — S §A1
- [x] `.env.example`, `README.md`, CI: lint → typecheck → unit tests → build
  - The script chain exists as `npm run ci` and now runs in the `frontend` job of
    `.github/workflows/ci.yml`, alongside Lighthouse and Playwright — see Phase 8.
- [x] `next.config.ts` security headers + CSP — S §A10, §A11

### Phase 1 — Public site (needs: backend Phase 2)
- [x] Public layout: header (name, practice areas, nav, Book CTA), footer (contact, terms/privacy, FAQ)
- [x] Landing page sections from PRD §5.1: profile, professional info, practice areas, services, pricing, CTA, contact, FAQ
- [x] `GET /services` wiring with server-side fetch + loading/error states
- [x] Service list + detail pages with `generateMetadata`
- [x] SEO: metadata, OG image, sitemap, `robots.txt`, JSON-LD `ProfessionalService`

### Phase 2 — Auth & guards (needs: backend Phase 1 + 4)
- [x] Login page: phone → OTP request → verify, 5:00 resend countdown, inline errors — S §A3
- [x] `lib/auth` cookie-aware session helper + `requireCustomer` / `requireAdmin`
- [x] `middleware.ts` redirects for `/dashboard/*`, `/bookings/*`, `/admin/*`
- [x] 401 interceptor in `api/client` with single refresh attempt
- [x] Admin login page (email/password) + logout

### Phase 3 — Booking wizard (needs: backend Phase 3 + 4 + 5 + 6)
- [x] `useBookingStore` (sessionStorage-persisted draft) + `features/booking` types
- [x] Step 1 service selection, URL sync `?service=`
- [x] Step 2 date strip + month picker, `GET /availability/dates`, `GET /availability/slots`, slot grid with keyboard nav and time-of-day grouping, no-availability state
- [x] Step 3 details form (RHF + Zod) + OTP verification inline
- [x] Step 4 appointment create → order create → Razorpay checkout (dynamic import) → verification poll loop → hold countdown banner
- [x] Step 5 confirmation: details, status, `.ics` download, receipt link, CTA to dashboard
- [x] Error paths: 409 slot-taken recovery with alternatives, payment failure retry, expired-hold handling — S §A8
- [x] Mobile layout pass at 360/390px; a11y pass on date + slot grids — S §B5

### Phase 4 — Client portal (needs: backend Phase 5)
- [x] Dashboard: upcoming/past/cancelled tabs, hero card, skeletons, empty states — S §A4
- [x] Booking detail page with status history timeline
- [x] Cancel flow with policy-aware refund messaging
- [x] Reschedule flow reusing the slot picker
- [x] Payment list + receipt view
- [x] Profile edit (email/phone re-verification)

### Phase 5 — Admin shell & dashboard (needs: backend Phase 1 + 9)
- [x] Admin layout: sidebar, topbar, responsive drawer, breadcrumbs
- [x] Shared `DataTable`, `StatusBadge`, `ConfirmDialog`, `KpiCard`, filter bar (URL-synced)
- [x] Dashboard: 4 KPIs + today's appointments list

### Phase 6 — Admin: appointments, calendar, clients (needs: backend Phase 3 + 5)
- [x] Appointments table: all PRD filters, debounced search, server pagination, row actions with optimistic updates + rollback
- [x] Appointment detail: summary, payment, status history, actions, audit trail
- [x] Calendar month/week/day views; day time-grid with Available/Booked/Blocked; block-time action; click-to-book
- [x] Clients table + profile (appointments, payments, notes autosave)

### Phase 7 — Admin: services, payments, reports, settings, audit (needs: backend Phase 2 + 6 + 9 + 1)
- [x] Services CRUD with drawer form + price-change warning
- [x] Payments table, detail, refund action
- [x] Reports with range selector (today/week/month/custom) + appointment & revenue cards
- [x] Settings: profile, FAQ, currency/timezone, reminder offsets, cancellation policy, working hours
- [x] Audit log table with before/after diff

### Phase 8 — Hardening
- [x] Loading skeletons for every route, error boundaries, 404 page
- [x] Empty states and offline/network-error handling throughout
- [x] SEO + OG for public pages; robots
- [x] Bundle budget check — `scripts/check-bundle.mjs`, per-route gzip budgets
- [x] Lighthouse tooling + recorded desktop result — `scripts/check-lighthouse.mjs` audits
  `/`, `/services`, `/book` against the production bundle and fails below 90 in any category
  or above 2500 ms LCP. Desktop (unthrottled) passes all three routes
  (`/book` performance 98, best-practices 96, LCP 65–1095 ms), and CI gates on it.
- [x] Lighthouse §8 target on the throttled mobile profile — **met, and CI now gates on it.**
  Mobile (Slow 4G, 4× CPU) scores `/` 98 / LCP 2414 ms, `/services` 100 / LCP 1665 ms,
  `/book` 99 / LCP 2264 ms; desktop is 100 / 33–44 ms on all three. Three causes, in order of
  what they were worth:
  1. **`browserslist` set to a modern floor** (`chrome/edge/firefox >= 111`, `safari >= 16.4`).
     With no `browserslist`, Next sized its output for its default list and shipped the legacy
     polyfill bundle; on a 1.6 Mbps connection that ~14 KB was competing with the render-blocking
     CSS and the webfonts for the same bandwidth. This was the single biggest win
     (LCP 3068 → 2266 ms on `/`) and also cleared the `legacy-javascript-insight` warning.
  2. **`/book` now server-renders its service list.** The wizard is a client component, so step 1
     was empty in the initial HTML and only filled in after the bundle booted and the API
     answered — the service descriptions were the largest text on the page, so they became the
     LCP element at ~3.8 s. `app/(booking)/book/page.tsx` fetches via the existing server query and
     passes the result down as `initialData`; `useActiveServices()` takes it so react-query
     serves the first render from cache. The page is also `force-dynamic` now: it lists live
     services and prices, and prerendering it either froze the list at build time or shipped an
     error state when the API was down during the build.
  3. **Fonts no longer trigger a swap repaint.** `app/layout.tsx` uses `display: 'optional'`, so
     the first paint is the LCP instead of a second paint after the webfont lands, and Geist Mono
     is no longer preloaded (it is only used on admin/customer detail screens and the confirmation
     step, so preloading it on public routes just took bandwidth from the fonts that do paint
     above the fold). Lora stays — it is genuinely above the fold (hero, section headers, footer).
  Measured with `LIGHTHOUSE_FORM_FACTOR=mobile npm run check:lighthouse` against Django and the API
  proxy, since these pages read live data; auditing the bundle alone measures empty states.
- [x] axe a11y sweep — `tests/unit/a11y.test.tsx`, 6 tests over the shared surfaces
- [x] Full keyboard booking test — `tests/unit/booking-wizard-keyboard.test.tsx` drives the
  assembled wizard (service → date → slot → details → OTP) end to end
- [x] E2E suite green in CI against a stacked backend — `playwright.config.ts` starts Django
  (`:8000`), the CORS/trailing-slash proxy (`:3399`), and the standalone Next server (`:3398`);
  22 specs pass and 10 backend-blocked contracts report as `test.fixme()` rather than failing.
  `scripts/verify-build-env.mjs` refuses to run against a bundle compiled for a different API
  origin, and `E2E_PYTHON` lets CI start Django without a repo virtualenv.
- [x] Frontend CI job — `frontend` job in `.github/workflows/ci.yml` runs lint → typecheck →
  vitest → build → bundle budget → Lighthouse → Playwright against Postgres/Redis, replacing
  the "CI runs backend only" gap below

### Phase 9 — Deploy
- [x] Container deploy: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `docs/deployment.md`
- [ ] Vercel (or container) deploy, env vars wired, preview deploys for PRs — no CI deploy
  job exists; the runbook describes the procedure but nothing is deployed
- [ ] Custom domain + HTTPS — documented in `docs/deployment.md` §4, not provisioned
- [x] Error monitoring wired, source maps — Sentry client/server configs,
  `instrumentation{,-client}.ts`, `sentry-cli` source-map upload vars in `.env.example`
- [ ] Run the full PRD §31 flow in staging and record it — `docs/deployment.md` §6 lists this
  as a pre-deploy manual step; no recording exists

### Deferred (post-MVP, PRD §30)
- [ ] WhatsApp/SMS notification preferences UI
- [ ] PDF invoice generation
- [ ] Coupon/promo UI
- [ ] Multi-provider admin views
- [ ] Dark mode
- [ ] Offline/PWA support
- [ ] i18n / multi-language

---

## 12. Risks

| Risk | Mitigation | Tracked in |
| --- | --- | --- |
| Slot list goes stale → user picks a taken time | Short `staleTime`, refetch on focus, handle 409 with a recovery path | S §A8, B §5 |
| Client-side polling feels janky | Bounded poll (5 × 1s) then a "still processing" state that keeps polling slowly | PRD §11 |
| Wizard state lost mid-payment | `sessionStorage` draft + server-side hold survives a reload | B §5 |
| Admin bundle grows with charts/reports | Dynamic import heavy views, keep the public bundle isolated | S §B5, C |
| Timezone drift between server strings and local display | Single `lib/utils/datetime.ts`; all server datetimes treated as UTC + tenant TZ | B §3, S §A8 |
| Two surfaces drift out of sync | Shared `features/*` hooks and `api/client`; no duplicate fetch logic in `app/` | B §4, prd §33 |
| Third-party payment SDK breaks the build | Dynamic import, wrapped behind a `lib/payments/` adapter, stubbed in tests | S §A11 |
| API contract drift | OpenAPI schema diff in CI against [`backend-plan.md`](./backend-plan.md) §4 | S §C |

## 13. Open questions

> **Settled:** D1 Razorpay, D2 manual refunds — see backend-plan.md §11.
> Carried over from [`backend-plan.md`](./backend-plan.md) §11, plus frontend-specific ones.
> The compliance questions in security.md §H also gate the booking flow
> (retention, consent) — treat all three lists as one backlog.

1. Razorpay or Cashfree? (Frontend needs the SDK choice up front.)
2. Is email required, or phone-OTP only? Changes step 3 validation.
3. Minimum notice for booking and for cancellation — shown to the client pre-submit.
4. Booking lead time and booking horizon — how far ahead the date picker should allow.
5. Fixed 30-minute grid or service-driven slots? Changes the slot grid component.
6. Should the public landing page carry a separate CMS/editor, or is `settings` enough for MVP?
7. Should receipts be printable HTML, PDF, or both?
8. Admin needs a printable day-schedule view?

## 14. Related documents

- [`prd.md`](./prd.md) — requirements, §33 traceability matrix
- [`backend-plan.md`](./backend-plan.md) — §4 API contract consumed by §3 here
- [`security.md`](./security.md) — §A11 frontend security, §B5 perf budgets, §C optimization proof
