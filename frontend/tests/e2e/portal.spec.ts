import { expect, test, type Page } from '@playwright/test'

import { readLatestOtp, uniquePhone } from './helpers'

/**
 * Sign in through the real form, using the backend's console OTP sender.
 *
 * `entryPath` matters: `/login` defaults its post-OTP destination to `/`, so a
 * spec that wants to land on a portal page has to enter through that page's
 * guard the way a real customer does - redirected to `/login?next=...`, then
 * back again. That round-trip is itself worth asserting.
 */
async function signInVia(page: Page, entryPath = '/login') {
  const phone = uniquePhone()
  await page.goto(entryPath)
  const expectedLogin = new URL(page.url()).pathname
  expect(expectedLogin).toBe('/login')

  await page.getByLabel(/mobile/i).fill(phone)
  await page.getByRole('button', { name: 'Send one-time password' }).click()
  const code = await readLatestOtp(phone)
  for (let digit = 1; digit <= code.length; digit += 1) {
    await page.getByLabel(`Digit ${digit}`).fill(code[digit - 1])
  }
  return expectedLogin
}

test.describe('customer portal', () => {
  test('signs in with a one-time password and returns to the guarded page', async ({
    page,
  }) => {
    // Enter through a guarded route so the `next` round-trip is exercised.
    await signInVia(page, '/bookings')

    await expect(page).toHaveURL(/\/bookings$/)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('shows the empty state when the customer has no appointments', async ({ page }) => {
    // `/bookings` is a redirect to the dashboard, so the empty state lives there.
    await signInVia(page, '/dashboard')

    await expect(page.getByText('No upcoming appointments').first()).toBeVisible()
  })

  test('signing in from the bare login page lands on the landing page', async ({ page }) => {
    await signInVia(page)

    // `/login` defaults its post-OTP destination to `/`.
    await expect(page).toHaveURL(/localhost:3398\/$/)
  })
})
