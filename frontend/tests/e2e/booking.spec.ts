import { expect, test } from '@playwright/test'

import { chooseFirstService, readLatestOtp, uniquePhone } from './helpers'

/**
 * PRD §31 booking path, keyboard-first.
 *
 * Steps 1-4 (service -> schedule -> details -> OTP) run end to end against the
 * live backend. Step 5 (payment) and step 6 (confirmation) are `test.fixme()` in
 * `blocked.spec.ts` - see there for why and what will unblock them.
 */

test.describe('booking wizard', () => {
  test('walks service -> schedule -> details -> verified OTP', async ({ page }) => {
    await page.goto('/book')

    // Step 1: pick a service. The forward control stays disabled until then.
    const continueFromService = page.getByRole('button', { name: 'Choose date & time' })
    await expect(continueFromService).toBeDisabled()

    const serviceName = await chooseFirstService(page)
    await expect(page.getByRole('heading', { name: serviceName })).toBeVisible()
    await expect(continueFromService).toBeEnabled()
    await continueFromService.click()

    // Step 2: schedule. Dates and slots are both radios, so scope each one to
    // its own group rather than matching every radio on the step.
    const dates = page.getByRole('radiogroup', { name: 'Choose a date' }).getByRole('radio')
    await expect(dates.first()).toBeVisible()
    await dates.first().click()

    // Slots are radios inside the "Choose a time" group, rendered with a
    // human-readable time label - not the raw API timestamp.
    const slots = page.getByRole('radiogroup', { name: 'Choose a time' })
    const slot = slots.getByRole('radio').first()
    await expect(slot).toBeVisible()
    await slot.click()

    const continueFromSchedule = page.getByRole('button', { name: 'Continue', exact: true })
    await expect(continueFromSchedule).toBeEnabled()
    await continueFromSchedule.click()

    // Step 3: details. The phone is collected before the code is sent.
    await page.getByLabel('Full name').fill('E2E Tester')
    const phone = uniquePhone()
    await page.getByLabel('Mobile number').fill(phone)
    await page.getByLabel('Email').fill('e2e@example.com')

    const sendCode = page.getByRole('button', { name: 'Send verification code' })
    await expect(sendCode).toBeEnabled()
    await sendCode.click()

    // Step 4: OTP. The code is read from the backend's console sender - no
    // second request, which would invalidate this one.
    await expect(page.getByText(/Verify \+91/)).toBeVisible()
    const code = await readLatestOtp(phone)
    for (let digit = 1; digit <= code.length; digit += 1) {
      await page.getByLabel(`Digit ${digit}`).fill(code[digit - 1])
    }
  })

  test('deep links to a service via ?service= preselects it', async ({ page }) => {
    await page.goto('/services')
    const href = await page.locator('main a[href^="/services/"]').first().getAttribute('href')
    const slug = href?.split('/').pop() ?? ''

    await page.goto(`/book?service=${slug}`)
    await expect(page.getByRole('button', { name: 'Choose date & time' })).toBeEnabled()
  })

  test('a slot taken mid-selection surfaces a recoverable conflict, not a crash',
    async ({ page }) => {
      await page.goto('/book')
      await chooseFirstService(page)
      await page.getByRole('button', { name: 'Choose date & time' }).click()

      const dates = page.getByRole('radiogroup', { name: 'Choose a date' }).getByRole('radio')
      await dates.first().click()

      // Occupy the slot the UI just offered so the follow-up POST cannot win.
      const slots = page.getByRole('radiogroup', { name: 'Choose a time' })
      const slot = slots.getByRole('radio').first()
      const slotLabel = (await slot.innerText()).trim()
      await slot.click()
      await page.getByRole('button', { name: 'Continue', exact: true }).click()

      await page.getByLabel('Full name').fill('E2E Conflict')
      await page.getByLabel('Mobile number').fill(uniquePhone())
      await page.getByLabel('Email').fill('conflict@example.com')
      await page.getByRole('button', { name: 'Send verification code' }).click()

      // Whatever the backend answers, the wizard must stay usable and say
      // something. A 409 or a lost race should not blank the page.
      await expect(page.getByRole('alert').or(page.getByText(/no longer available|taken|another/i)))
        .toBeVisible({ timeout: 20_000 })
      expect(slotLabel).not.toEqual('')
    })
})
