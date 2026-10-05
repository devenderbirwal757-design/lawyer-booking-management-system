import { expect, test } from '@playwright/test'

import { readLatestOtp, uniquePhone } from './helpers'

/**
 * Surfaces that cannot be exercised end to end yet because the backend does not
 * expose them, or because production-like payment credentials are missing.
 *
 * Each test calls `test.fixme()` as its first statement, so Playwright reports
 * them as known-blocked instead of failing the run. They stay in the repo as
 * executable documentation of the contract: delete the `test.fixme()` line when
 * the corresponding backend task lands and the assertion becomes a real gate.
 *
 * Backend work required, per `frontend-plan.md` (Phase 8 / known gaps):
 *  - `admin/reports/dashboard` -> dashboard KPIs
 *  - `admin/calendar` -> calendar view
 *  - `admin/customers/*` -> clients list/detail
 *  - `admin/reports/appointments|revenue` -> reports
 *  - `admin/audit-logs` -> audit log page
 *  - `admin/settings` -> settings page
 *  - `me/profile` and customer `auth/logout|refresh` -> profile page
 *  - Razorpay test credentials + webhook secret -> payment + confirmation
 */
test.describe('@blocked backend contracts', () => {
  test('admin dashboard KPIs (blocked - missing admin/reports/dashboard)', async ({ page }) => {
    test.fixme()
    await page.goto('/admin')
    await expect(page.getByText(/KPI|revenue|appointments/i).first()).toBeVisible()
  })

  test('admin calendar (blocked - missing admin/calendar)', async ({ page }) => {
    test.fixme()
    await page.goto('/admin/calendar')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('admin clients list (blocked - missing admin/customers endpoints)', async ({ page }) => {
    test.fixme()
    await page.goto('/admin/clients')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('admin client detail (blocked - missing admin/customers/:id)', async ({ page }) => {
    test.fixme()
    await page.goto('/admin/clients/1')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('admin reports (blocked - missing admin/reports/*)', async ({ page }) => {
    test.fixme()
    await page.goto('/admin/reports')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('admin audit log (blocked - missing admin/audit-logs)', async ({ page }) => {
    test.fixme()
    await page.goto('/admin/audit')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('admin settings (blocked - missing admin/settings)', async ({ page }) => {
    test.fixme()
    await page.goto('/admin/settings')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('customer profile (blocked - missing me/profile)', async ({ page }) => {
    test.fixme()
    await page.goto('/profile')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('customer auth logout/refresh contract (blocked - backend contract mismatch)',
    async ({ page }) => {
      test.fixme()
      const phone = uniquePhone()
      await page.goto('/login')
      await page.getByLabel(/mobile/i).fill(phone)
      await page.getByRole('button', { name: 'Send one-time password' }).click()
      const code = await readLatestOtp(phone)
      for (let digit = 1; digit <= code.length; digit += 1) {
        await page.getByLabel(`Digit ${digit}`).fill(code[digit - 1])
      }
      // `/login` defaults its post-OTP destination to `/`.
      await expect(page).toHaveURL(/localhost:\d+\/$/)

      // Customer logout must reach the backend contract in PRD §13 and land
      // back on the login page.
      await page.getByRole('button', { name: /log out|sign out/i }).click()
      await expect(page).toHaveURL(/\/login/)
    })

  test('booking payment + confirmation (blocked - Razorpay test credentials)',
    async ({ page }) => {
      // Payment needs real test-mode keys plus a webhook secret; with the
      // backend's blank gateway config the order call cannot succeed, so the
      // step stays fixed until credentials exist.
      test.fixme()
      await page.goto('/book')
      await expect(page.getByRole('button', { name: 'Choose date & time' })).toBeDisabled()
    })
})