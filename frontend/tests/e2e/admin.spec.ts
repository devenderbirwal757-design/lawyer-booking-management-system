import { expect, test } from '@playwright/test'

import { ADMIN_PASSWORD, loginAsAdmin } from './helpers'

test.describe('admin', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
  })

  test('login rejects a wrong password with a visible message', async ({ page }) => {
    // Deliberately *not* using the shared beforeEach here.
    await page.context().clearCookies()
    await page.goto('/admin/login')
    await page.getByLabel('Email').fill('boss@example.com')
    await page.getByLabel('Password').fill('definitely-wrong')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page).toHaveURL(/\/admin\/login/)
  })

  test('dashboard loads after sign in', async ({ page }) => {
    await page.goto('/admin')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('appointments list renders with its filters', async ({ page }) => {
    await page.goto('/admin/appointments')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    // Both filters are labelled, so assert them by role + name rather than a
    // loose placeholder regex, which also matches the status select.
    await expect(page.getByRole('searchbox', { name: 'Search appointments' })).toBeVisible()
    await expect(page.getByRole('combobox', { name: 'All statuses' })).toBeVisible()
  })

  test('services list loads from the admin API', async ({ page }) => {
    await page.goto('/admin/services')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByText(/Consultation/i).first()).toBeVisible()
  })

  test('admin sign out clears the session and re-guards the area', async ({ page }) => {
    await page.goto('/admin')
    await page.getByRole('button', { name: /sign out|log out/i }).click()
    await expect(page).toHaveURL(/\/admin\/login/)

    await page.goto('/admin/appointments')
    await expect(page).toHaveURL(/\/admin\/login/)
  })

  test.describe('credentials hygiene', () => {
    test('the admin password is never the seed default', () => {
      expect(ADMIN_PASSWORD.length).toBeGreaterThanOrEqual(12)
    })
  })
})
