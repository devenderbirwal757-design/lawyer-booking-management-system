import { expect, test } from '@playwright/test'

/**
 * Guards are middleware behaviour, so they are worth asserting directly: a
 * regression here leaks another customer's booking list rather than failing
 * visibly.
 */
test.describe('session guards', () => {
  for (const [path, loginPath] of [
    ['/dashboard', '/login'],
    ['/bookings', '/login'],
    ['/payments', '/login'],
    ['/profile', '/login'],
    ['/admin', '/admin/login'],
    ['/admin/appointments', '/admin/login'],
  ] as const) {
    test(`${path} redirects an anonymous visitor to ${loginPath}`, async ({ page }) => {
      await page.goto(path)
      // The guard appends `?next=` so the customer lands back where they were;
      // assert the pathname rather than the full URL, which carries the origin.
      await page.waitForURL((url) => url.pathname === loginPath)
      expect(new URL(page.url()).searchParams.get('next')).toBe(path)
    })
  }
})
