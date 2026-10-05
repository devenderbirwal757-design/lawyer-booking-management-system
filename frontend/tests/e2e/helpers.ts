import { expect, type APIRequestContext, type Page } from '@playwright/test'

import { readFile } from 'node:fs/promises'

/**
 * Shared helpers for the Phase 8 end-to-end suite.
 *
 * Two of these exist because the backend deliberately refuses to make life easy:
 *
 *  - `otpCodeFor` reads the code out of the backend's stdout. The OTP is stored
 *    as a salted digest and is never returned by the API (S §A3), so the console
 *    sender is the only supported way to complete a login in a test. That is the
 *    documented dev flow, not a workaround for a missing endpoint.
 *  - `stubRazorpay` replaces the gateway checkout script. No Razorpay test
 *    credentials are configured, so the payment step cannot reach the real
 *    gateway; the specs that depend on it are marked `@blocked` and this helper
 *    is what will let them run once the backend team supplies credentials.
 */

export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'boss@example.com'
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'e2e-admin-password'

/** Where the backend's stdout is captured. Overridden in CI. */
const BACKEND_LOG = process.env.E2E_BACKEND_LOG ?? '/tmp/backend-e2e.log'

/**
 * Where the API proxy is listening; OTP calls must bypass the Next origin.
 * Must stay `localhost` to match the inlined `NEXT_PUBLIC_API_URL` - see the
 * note in `playwright.config.ts`.
 */
export const apiOrigin = `http://localhost:${process.env.TEST_PROXY_PORT ?? 3399}`

/**
 * A fresh, valid customer phone number for each caller.
 *
 * Numbers must not be shared between specs: the backend enforces a per-phone
 * OTP resend cooldown, so a second request for a number another spec just used
 * is rejected and the captured code is already spent. Handing out a unique
 * number per call keeps every spec independent of execution order, and of how
 * many times the suite is re-run against the same database.
 */
let phoneSequence = 0
export function uniquePhone(): string {
  phoneSequence += 1
  // `9` + 7 random digits + a 2-digit sequence suffix keeps it 10 digits long,
  // starts with a valid Indian mobile prefix, and stays unique within a run.
  const random = String(Math.floor(Math.random() * 10_000_000)).padStart(7, '0')
  return `9${random}${String(phoneSequence % 100).padStart(2, '0')}`
}

export async function otpCodeFor(
  request: APIRequestContext,
  phone: string,
): Promise<string> {
  const response = await request.post(`${apiOrigin}/api/v1/auth/otp/request`, {
    data: { phone },
  })
  expect(response.ok(), 'OTP request should be accepted').toBeTruthy()
  return readLatestOtp(phone)
}

/**
 * Read the most recent code the backend printed for `phone` without issuing a
 * new one.
 *
 * Use this whenever the spec has *already* driven the send through the UI:
 * requesting a second code would invalidate the first and trip the per-phone
 * send-window throttle.
 *
 * The backend normalises the number to E.164 before printing
 * (`[dev-otp] OTP for +919876500077: 247170`), so the match allows a country
 * code and `+` in front of whatever the spec typed.
 */
export async function readLatestOtp(phone: string): Promise<string> {
  const digits = phone.replace(/\D/g, '')
  const pattern = new RegExp(`\\[dev-otp\\] OTP for \\+?\\d*${digits}: (\\d{6})`, 'g')
  const deadline = Date.now() + 15_000
  while (Date.now() < deadline) {
    const log = await readFile(BACKEND_LOG, 'utf8').catch(() => '')
    // The log accumulates across specs and reruns, so the *last* line for this
    // phone is the live code; the first would be a stale one.
    const matches = [...log.matchAll(pattern)]
    const latest = matches.at(-1)
    if (latest) return latest[1]
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  throw new Error(
    `No [dev-otp] line for ${phone} in ${BACKEND_LOG}. Is the backend running ` +
      `unbuffered (python -u) with DJANGO_OTP_SMS_BACKEND=console and its stdout ` +
      `redirected to that file?`,
  )
}

/**
 * Enter a code that the UI's own "send" already triggered. Deliberately does
 * *not* request a new code - see `readLatestOtp`.
 */
export async function enterBookingCode(
  page: Page,
  request: APIRequestContext,
  phone: string,
): Promise<void> {
  const code = await otpCodeFor(request, phone)
  for (let digit = 1; digit <= code.length; digit += 1) {
    await page.getByLabel(`Digit ${digit}`).fill(code[digit - 1])
  }
}

/** Sign an admin in through the real form so the cookie path is exercised. */
export async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto('/admin/login')
  await page.getByLabel('Email').fill(ADMIN_EMAIL)
  await page.getByLabel('Password').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  // The shell sends you to `/admin/dashboard`; anything else inside `/admin`
  // that is not the login page means the session was established. Matching on
  // the pathname rather than a trailing-slash regex avoids asserting on the
  // dashboard route specifically, which is not what this helper is testing.
  await page.waitForURL(
    (url) => url.pathname.startsWith('/admin') && url.pathname !== '/admin/login',
    { timeout: 15_000 }
  )
}

/**
 * Replace Razorpay's checkout script with an instance that resolves a payment
 * immediately. Kept honest: it produces the same callback shape the real
 * gateway does, so `openRazorpay`'s handler runs unmodified.
 */
export async function stubRazorpay(page: Page): Promise<void> {
  await page.route('https://checkout.razorpay.com/v1/checkout.js', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/javascript',
      body: `
        window.Razorpay = class {
          constructor(options) { this.options = options }
          open() {
            const id = 'pay_e2e_' + Date.now()
            this.options.handler({
              razorpay_payment_id: id,
              razorpay_order_id: this.options.order_id,
              razorpay_signature: 'e2e-signature'
            })
          }
          close() {}
        }
      `,
    })
  })
}

/** First service card on the booking wizard, by its heading. */
export async function chooseFirstService(page: Page): Promise<string> {
  const card = page.getByRole('button').filter({ has: page.locator('h3') }).first()
  const name = (await card.locator('h3').innerText()).trim()
  await card.click()
  return name
}
