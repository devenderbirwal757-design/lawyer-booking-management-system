import { expect, test } from '@playwright/test'

test.describe('public pages', () => {
  test('landing page renders the seeded services from the API', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    // Service cards come from GET /services, so their presence proves the
    // browser -> proxy -> backend path rather than static copy.
    await expect(page.locator('main a[href^="/services/"]').first()).toBeVisible()
  })

  test('service index lists services and links to a detail page', async ({ page }) => {
    await page.goto('/services')

    const firstService = page.locator('main a[href^="/services/"]').first()
    await expect(firstService).toBeVisible()
    await firstService.click()

    await expect(page).toHaveURL(/\/services\/[a-z0-9-]+$/)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('service detail exposes StructuredData for SEO', async ({ page }) => {
    await page.goto('/services')
    await page.locator('main a[href^="/services/"]').first().click()

    const jsonLd = page.locator('script[type="application/ld+json"]').first()
    await expect(jsonLd).toHaveCount(1)
    const parsed = JSON.parse((await jsonLd.textContent()) ?? '{}')
    expect(parsed['@type']).toBe('Service')
    expect(parsed.name).toBeTruthy()
  })

  test('robots and sitemap are served', async ({ request }) => {
    const robots = await request.get('/robots.txt')
    expect(robots.ok()).toBeTruthy()
    expect(await robots.text()).toContain('Sitemap')

    const sitemap = await request.get('/sitemap.xml')
    expect(sitemap.ok()).toBeTruthy()
    expect(await sitemap.text()).toContain('<urlset')
  })
})
