PRD — Lawyer Booking & Management System

Version: 1.0
Product Type: Single-Lawyer Appointment & Client Management System
Primary Users: Lawyer/Admin + Clients
Status: MVP
Architecture Goal: Reusable backend for future consultation businesses

> **Companion documents — read these alongside this PRD**
>
> | Document | Purpose | Owner |
> | --- | --- | --- |
> | [`backend-plan.md`](./backend-plan.md) | Django/DRF architecture, data model, API surface, phased checklist | Backend |
> | [`frontend-plan.md`](./frontend-plan.md) | Next.js architecture, booking wizard, admin console, phased checklist | Frontend |
> | [`security.md`](./security.md) | Security / performance / optimization test plan and release gates | QA |
>
> Every requirement in §1–§32 is mapped to its backend phase, frontend phase, and security
> test in the **Requirement Traceability Matrix** at the end of this file. When a requirement
> changes here, update the three plans in the same commit.
>
> That consistency is machine-checked, not a convention:
> ```
> python3 scripts/check_docs.py
> ```
> It fails if a PRD section has no matrix row, a row points at a section that does not exist,
> a relative link breaks, a `B §5` / `S §A4` reference does not resolve, a section number is
> duplicated, or a document stops linking to its siblings. Runs in CI
> (`.github/workflows/docs.yml`) and as a pre-commit hook.

1. Product Overview

A web-based booking and management system for a single lawyer.

Clients can:

View available consultation services
Select an available date/time
Enter their details
Pay online
Receive booking confirmation
Log in and view their bookings
View booking/payment details
Cancel or reschedule where permitted

The lawyer/admin can:

View and manage appointments
Manage clients
Manage services and pricing
Configure availability
View payments
Manage cancellations/rescheduling
View basic reports
Manage system settings
Important architectural decision

Although the UI is lawyer-specific, the backend should use generic concepts such as:

Provider
Customer
Service
Appointment
Payment
Availability
Notification

rather than hard-coding the entire backend around "lawyer."

2. Goals
Primary goals
Allow clients to book a lawyer consultation online.
Allow clients to pay online during booking.
Give the lawyer one centralized dashboard for managing bookings.
Allow clients to see their own booking history.
Prevent double-booking.
Provide reliable payment verification.
Make the backend reusable for future consultation-based businesses.
Non-goals for MVP

The first version will not include:

Multiple lawyers
Lawyer marketplace
Lawyer-to-lawyer communication
Full legal case-management system
Court case tracking
Legal document automation
Video consultation
Mobile application
Subscription plans

These can be added later.

3. User Roles
Admin / Lawyer

The single lawyer acts as the system administrator.

Can:

Manage appointments
Manage clients
Manage services
Manage availability
View payments
View reports
Configure settings
Client

Can:

Browse services
Book an appointment
Make payment
View bookings
View payment status
Cancel/reschedule according to rules
Manage basic profile information
4. High-Level User Flow
Client booking
Landing Page
     ↓
Select Service
     ↓
Select Date
     ↓
Select Available Time
     ↓
Enter Client Details
     ↓
Phone/Email Verification
     ↓
Payment
     ↓
Payment Verification
     ↓
Booking Confirmed
     ↓
Client Dashboard
5. Client Features
5.1 Landing Page

The lawyer's public website should contain:

Lawyer profile
Professional information
Practice areas
Services
Consultation pricing
Booking CTA
Contact information
Basic FAQ
Terms/privacy links

Lawyer-specific information will be configurable later.

5.2 Services

Example:

Service	Duration	Price
Initial Consultation	30 min	₹500
Follow-up Consultation	30 min	₹300
Document Consultation	45 min	₹700

Admin should be able to create/edit/delete services.

Service fields:

id
name
description
duration
price
currency
status
6. Availability & Scheduling

The lawyer can configure working hours.

Example:

Monday
10:00 AM – 6:00 PM

Tuesday
10:00 AM – 6:00 PM

Wednesday
10:00 AM – 2:00 PM

The system generates bookable slots according to:

Working Hours
+
Service Duration
+
Existing Appointments
+
Blocked Times
=
Available Slots
Example

Working hours:

10:00 – 13:00

Service duration:

30 minutes

Available:

10:00
10:30
11:00
11:30
12:00
12:30
7. Prevent Double Booking

This is a critical requirement.

If two clients attempt to book:

15 October
11:30 AM

simultaneously, only one booking can successfully obtain that slot.

The backend must enforce this using:

Database constraints/transactions
Temporary booking locks where required
Server-side availability validation

Frontend availability alone is not sufficient.

8. Appointment Lifecycle

Appointment statuses:

PENDING_PAYMENT
CONFIRMED
COMPLETED
CANCELLED
NO_SHOW
RESCHEDULED

Basic flow:

PENDING_PAYMENT
       ↓
    CONFIRMED
       ↓
    COMPLETED

Cancellation:

CONFIRMED
    ↓
CANCELLED
9. Client Account

The client should not need to manually register before booking.

Recommended flow:

Enter phone number
       ↓
OTP verification
       ↓
Continue booking
       ↓
Account automatically created/updated

This reduces booking friction.

Client Dashboard
My Dashboard

Upcoming
Past
Cancelled

Upcoming Appointment
─────────────────────
15 Oct 2026
11:30 AM

Legal Consultation
₹500
Paid

[View Details]
10. Booking Details

Client should see:

Booking ID
Service
Date
Time
Lawyer
Amount
Payment status
Booking status
Created date

Example:

Booking #BK10293

Legal Consultation

15 October 2026
11:30 AM

Amount: ₹500
Payment: Paid
Status: Confirmed
11. Payment System

Payment should be handled server-side.

Flow
Client
  ↓
Backend creates payment order
  ↓
Payment Gateway
  ↓
Client completes payment
  ↓
Gateway webhook
  ↓
Backend verifies transaction
  ↓
Payment marked successful
  ↓
Appointment confirmed

The frontend must never be trusted to declare a payment successful.

Payment abstraction

The backend should use a generic interface:

PaymentService
      │
      ├── Razorpay
      ├── Cashfree
      └── Other Gateway

For the first implementation, one Indian payment gateway can be selected.

12. Payment Data

Payment record:

id
appointment_id
customer_id
amount
currency
gateway
gateway_order_id
gateway_payment_id
status
paid_at
created_at

Statuses:

CREATED
PENDING
SUCCESS
FAILED
REFUNDED
13. Admin Dashboard

The admin dashboard is the primary management interface.

Dashboard
┌─────────────────────────────────────────┐
│ Dashboard                               │
├──────────┬──────────┬──────────┬────────┤
│ Today    │ Upcoming │ Clients  │ Revenue│
│    6     │    18    │   124    │ ₹9,500 │
└──────────┴──────────┴──────────┴────────┘

Today's appointments:

10:00  Rahul Kumar     Consultation   Paid
11:30  Amit Sharma     Consultation   Paid
02:00  Neha Patel      Follow-up      Paid
14. Appointment Management

Admin can:

View appointments
Filter by date
Search client
View appointment details
Confirm
Cancel
Reschedule
Mark completed
Mark no-show

Filters:

Date
Status
Service
Payment status
Client
15. Client Management

Admin can view:

Clients
───────────────
Rahul Kumar
Amit Sharma
Neha Patel

Client profile:

Name
Phone
Email

Appointments
Payment History
Notes
Important

For MVP, keep client notes generic.

Do not build a full legal case-management system into the booking engine.

16. Calendar

Admin gets:

Monthly calendar
Weekly calendar
Daily schedule

Example:

October 2026

Mon Tue Wed Thu Fri Sat Sun
             1   2   3   4
5   6   7   8   9  10  11
12 13  14  15  16  17  18

Selecting a date shows:

10:00 Available
10:30 Booked
11:00 Available
11:30 Booked
12:00 Blocked
17. Availability Management

Admin can:

Configure recurring availability
Monday
10 AM – 6 PM

Tuesday
10 AM – 6 PM
Add exceptions
15 October
2 PM – 6 PM
Blocked
Full-day blocking
20 October
Unavailable
18. Notifications

MVP notification channels:

Email
Booking confirmation
Payment confirmation
Cancellation
Rescheduling
Appointment reminder
Optional later
WhatsApp
SMS

Notification architecture should be provider-independent:

NotificationService
       │
       ├── Email
       ├── SMS
       └── WhatsApp
19. Appointment Reminders

Example:

24 hours before appointment
        ↓
Reminder

1 hour before appointment
        ↓
Reminder

This should be handled asynchronously through a background job system.

20. Reports

MVP reports:

Appointment report
Total bookings
Completed
Cancelled
No-show
Revenue report
Total revenue
Paid
Pending
Refunded
Date filtering
Today
This week
This month
Custom range
21. Authentication & Security
Admin

Secure email/password authentication.

Potential future:

2FA
Passkeys
Client

Phone OTP or email verification.

Authorization

The backend must enforce ownership.

A client must only access:

their own profile
their own appointments
their own payments

Never rely on frontend restrictions.

22. Audit Logging

Important admin actions should be recorded.

Example:

Admin changed appointment

Appointment: BK10293

Previous:
11:00 AM

New:
11:30 AM

Timestamp:
28 Sep 2026 10:32

Audit events:

Appointment modified
Payment status changed
Client information modified
Service modified
Availability modified
Cancellation
Refund
23. Database Architecture

Core schema:

tenants
users
customers
providers
services
availability_rules
availability_exceptions
appointments
appointment_status_history
payments
notifications
notification_templates
audit_logs

Even though V1 has only one lawyer, keep tenant_id and provider_id in the core model where appropriate.

This allows future reuse.

Example
Tenant
   │
   ├── Provider
   │
   ├── Customers
   │
   ├── Services
   │
   ├── Appointments
   │
   └── Payments
24. Recommended Tech Stack

I'd use a modern, boring-but-reliable stack.

Frontend

Next.js + TypeScript

React
App Router
Tailwind CSS
shadcn/ui
React Hook Form
Zod
TanStack Query
Backend

Django + Django REST Framework

Why:

Mature authentication ecosystem
Excellent ORM
Strong security defaults
Admin capabilities
PostgreSQL support
Good fit for business applications
Database

PostgreSQL

Background Jobs

Celery + Redis

Used for:

Appointment reminders
Emails
Notifications
Payment-related asynchronous tasks
Infrastructure
Frontend → Next.js
Backend  → Django
Database → PostgreSQL
Cache    → Redis
Storage  → S3-compatible object storage
25. Backend Structure

I would structure it approximately like:

backend/
│
├── config/
│
├── apps/
│   ├── accounts/
│   ├── tenants/
│   ├── providers/
│   ├── customers/
│   ├── services/
│   ├── scheduling/
│   ├── appointments/
│   ├── payments/
│   ├── notifications/
│   ├── reports/
│   └── audit/
│
├── common/
│   ├── permissions/
│   ├── exceptions/
│   ├── pagination/
│   └── utilities/
│
└── manage.py
26. API Structure

Version from day one:

/api/v1/

Core endpoints:

/auth/
/customers/
/providers/
/services/
/availability/
/appointments/
/payments/
/notifications/
/reports/

Examples:

GET /api/v1/services
GET /api/v1/availability?date=2026-10-15&service_id=3
POST /api/v1/appointments
POST /api/v1/payments/create-order
POST /api/v1/payments/webhook
GET /api/v1/me/appointments
27. Frontend Structure
frontend/
│
├── app/
│   ├── (public)/
│   │   ├── page.tsx
│   │   ├── services/
│   │   └── booking/
│   │
│   ├── (customer)/
│   │   ├── dashboard/
│   │   ├── bookings/
│   │   └── profile/
│   │
│   └── admin/
│       ├── dashboard/
│       ├── appointments/
│       ├── clients/
│       ├── services/
│       ├── calendar/
│       ├── payments/
│       └── settings/
│
├── components/
├── features/
├── lib/
├── services/
└── types/
28. UI/UX Requirements

Design should be:

Mobile-first
Responsive
Minimal
Professional
Fast
Accessible
Client

Booking should require as few steps as practical:

Service
 ↓
Date & Time
 ↓
Details
 ↓
Payment
 ↓
Confirmation
Admin

Desktop-first dashboard with responsive mobile support.

29. Non-Functional Requirements
Performance

Target:

Fast initial page load
API responses generally <500ms under normal load
Efficient database queries
Server-side pagination
Reliability

Payment and appointment operations must be transactional.

Security
HTTPS
Secure cookies/tokens
Password hashing
Rate limiting
Input validation
Authorization checks
Webhook signature verification
Audit logging
Database backups
Scalability

The initial deployment can be small, but architecture should allow:

1 Lawyer
      ↓
Multiple lawyers
      ↓
Multiple businesses
      ↓
Multiple professions

without rewriting the booking engine.

30. MVP Scope
Must have
✓ Lawyer profile
✓ Services
✓ Client booking
✓ Availability
✓ Calendar
✓ Client accounts
✓ Client booking history
✓ Admin dashboard
✓ Appointment management
✓ Online payment
✓ Payment verification
✓ Email confirmation
✓ Appointment reminders
✓ Client management
✓ Basic reports
✓ Authentication
✓ Audit logs
Later
○ WhatsApp
○ SMS
○ Video consultation
○ Invoices
○ Refund automation
○ Coupons
○ Case management
○ Documents
○ Court/hearing management
○ Multiple lawyers
○ Mobile app
○ Profession templates
31. MVP Success Criteria

The MVP is successful when this complete flow works reliably:

Client
  ↓
Selects legal consultation
  ↓
Selects available slot
  ↓
Provides phone/details
  ↓
Pays ₹X
  ↓
Payment verified by backend
  ↓
Appointment confirmed
  ↓
Client sees booking
  ↓
Lawyer sees booking in dashboard
  ↓
Reminder is sent
  ↓
Lawyer marks appointment completed

And critically:

Two clients cannot successfully book
the same slot.
32. Future-Proofing Principle

The lawyer-specific parts should stay at the configuration/domain layer, while the core remains generic.

                CORE
────────────────────────────────
Customer
Provider
Service
Appointment
Availability
Payment
Notification
Authentication
Tenant
────────────────────────────────
                 │
                 ▼
          LEGAL CONFIGURATION
────────────────────────────────
Client
Advocate
Consultation
Legal Services
────────────────────────────────

Later:

                 CORE
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
      LEGAL    MEDICAL  CONSULTING


33. Requirement Traceability Matrix

Single source of truth for "where is each requirement implemented and tested".
Change a requirement in 1-32, then update the three rows it touches.
Decisions taken are logged in backend-plan.md §11 (D1 Razorpay, D2 manual refunds, D3 phone-OTP only, D4 service-driven slots, D5 automatic blocking).
This table is machine-checked: `python3 scripts/check_docs.py` fails if a PRD
section has no row here, or if a row points at a section that does not exist.

Legend
B = backend-plan.md | F = frontend-plan.md | S = security.md
Always prefix a reference with its document: `B §5` is backend-plan section 5,
`S §A4` is security.md section A4. "Part B"/"Part C" in security.md may be
written as `S §B` / `S §C`. "Phase N" refers to a checklist phase within that
document.

| PRD | Requirement | Backend | Frontend | Security / Perf test |
| --- | --- | --- | --- | --- |
| 1 | Product overview (client + lawyer capabilities) | B §0 domain model | F §0 scope | - |
| 1 | Generic core, not hard-coded "lawyer" | B §0, B §3 Provider/Customer | F §0 | S §A4 tenant isolation |
| 2 | Prevent double-booking | B §5 (4 layers, PG exclusion) | F §4 step 2, 409 recovery | S §A8 concurrency test, S §B2 booking spike |
| 2 | Reliable payment verification | B §6 | F §4 step 4 poll | S §A5 |
| 2 | Backend reusable for other businesses | B §3 tenant_id everywhere | - | S §A4 cross-tenant test |
| 3 | Roles: admin vs client | B §1, B §4 | F §2 auth, F §5 admin | S §A2, S §A3, S §A4 |
| 4 | Client booking flow | B §4 endpoints | F §4 wizard | S §B2, Playwright full-flow |
| 5.1 | Landing page content | - | F §11 Phase 1 | S §B5 Lighthouse budget, S §A6 XSS |
| 5.2 | Services CRUD, duration/price | B §2 | F §5 admin services | S §A8 negative price |
| 6 | Working hours + slot generation | B §3 SlotService | F §4 date/slot picker | S §B3 EXPLAIN, slot-engine unit tests |
| 6 | **Decision:** service-driven slots, not fixed 30-min (D4) | B §3.1 | F §4 step 2 | S §B3 |
| 6 | **Decision:** booked times block automatically (D5) | B §5.5 | F §6 block-time copy | S §A8 invariant |
| 7 | **Prevent double booking (critical)** | B §5 all 4 layers | F §4 stale refetch | S §A8 (S0), S §B2 |
| 8 | Appointment lifecycle statuses | B §5 state machine | F §5 status badges | S §A8 illegal transitions |
| 9 | Client account via phone OTP, no manual register | B §4 OTP | F §4 step 3, F §2 | S §A3 enumeration, hashing, rate limits |
| 9 | **Decision:** phone-OTP only, email optional (D3) | B §6.3 | F §4 step 3 | S §A3 |
| 9 | **Consequence:** §30 email confirmation + §19 reminders become best-effort | B §6.3 | F §4 step 3, §5 | S §A9 |
| 9 | Client dashboard (upcoming/past/cancelled) | B §4 /me/appointments | F §5 dashboard | S §A4 IDOR |
| 10 | Booking details shown to client | B §4 detail serializer | F §5 detail page | S §A4 |
| 11 | Payment server-side, webhook-verified | B §6 | F §4 step 4 | S §A5 signature, replay, amount |
| 11 | Payment gateway abstraction | B §6 PaymentGateway ABC | F §4 SDK adapter | S §A5 mode isolation |
| 11 | Gateway decision: Razorpay (D1) | B §6 RazorpayGateway live | F §4 Razorpay SDK | S §A5 |
| 11 | Refunds are manual (D2) | B §6.2 two admin actions | F §5 honest cancel copy | S §A5 |
| 12 | Payment data fields + statuses | B §3 Payment* models | F §5 payment list | S §A5 unique gateway ids, Decimal |
| 12 | **Deviation:** add `EXPIRED` + `CANCELLED` to the 5 PRD statuses | B §6.1 | F §4 hold-expiry copy | S §A5 |
| 13 | Admin dashboard KPIs | B §9 /admin/reports/dashboard | F §6 dashboard | S §B2 admin browse |
| 14 | Appointment management + filters | B §5 admin endpoints | F §6 appointments table | S §A4, S §B3 pagination |
| 15 | Client management + generic notes | B §4 /admin/customers | F §6 client profile | S §A4 IDOR, S §A6 XSS in notes |
| 16 | Calendar month/week/day | B §4 /admin/calendar | F §6 calendar views | S §B3 index usage |
| 17 | Availability rules + exceptions + blocking | B §3 | F §6 block-time action | S §A7 scrape throttle |
| 18 | Notifications, email MVP, provider-independent | B §7 | F §5 prefs (deferred) | S §A9 no PII in logs |
| 19 | Reminders at 24h and 1h, async | B §8 beat task, idempotent | - | S §B4 burst 10k, no double-send |
| 20 | Reports: appointment + revenue, date ranges | B §9 | F §6 admin console, F §11 Phase 7 | S §B2 report load, S §C aggregation |
| 21 | Auth + ownership enforcement | B §8 | F §2 guards (UX only) | S §A2, S §A3, S §A4 |
| 21 | Rate limiting, validation, webhook sig, backups | B §8 | F §9 | S §A1, S §A5, S §A6, S §A7, S §A9, S §A10 |
| 22 | Audit logging of admin actions | B §1 audit app | F §6 audit log page | S §A9 audit immutability |
| 23 | Database architecture, tenant_id retained | B §3 | - | S §A4 |
| 24 | Recommended tech stack | B §0, B §2 | F §0 | S §2 tooling |
| 25 | Backend structure | B §2 | - | S §C |
| 26 | API structure, versioned from day one | B §4 | F §3 typed client | S §A12 no browsable API in prod |
| 27 | Frontend structure | - | F §2 | S §B5 bundle budgets |
| 28 | UI/UX: mobile-first, minimal, accessible | - | F §1, F §7 | S §B5 Lighthouse >= 90, axe, INP/CLS |
| 29 | Perf < 500ms, server-side pagination | B §3 indexes | F §8 | S §B2, S §B3, S §C |
| 29 | Scalability 1 lawyer to many businesses | B §3 tenancy | - | S §A4 |
| 30 | MVP scope (must-have vs later) | B §1, B §11 deferred | F §1, F §12 deferred | S §E pre-launch |
| 31 | **MVP success criteria end-to-end** | B §1 Phases 0-10 | F §11 Phases 0-9 | S §E, Playwright full-flow, S §B2 |
| 31 | "Two clients cannot book the same slot" | B §5 | F §4 | S §A8 (S0 release gate) |
| 32 | Future-proofing: core generic, config at edge | B §0, B §3 Tenant.profile | - | S §A4 |

Non-functional targets referenced above are defined in security.md Part B, and the
release gates in security.md §1. Open product questions that would change all
three plans are consolidated in backend-plan.md §11, frontend-plan.md §13,
and security.md §H.