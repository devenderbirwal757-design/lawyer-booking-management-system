import { describe, expect, it } from 'vitest'

import { serviceSchema } from '@/features/services/schema'

/**
 * `api.get(path, { schema })` only validates if the option actually reaches the
 * request helper.
 *
 * The helper read `schema` from a second parameter that no `api.*` method ever
 * passed, so it was always `undefined`: every response came back unvalidated.
 * The visible symptom was a decimal-string `price_amount` reaching `formatMoney`
 * and throwing `formatMoney expects a finite number`, which took the whole
 * `/book` page down to its error boundary.
 *
 * This test pins the coercion the schema is responsible for. The plumbing is
 * covered end to end by the booking E2E specs.
 */
describe('service price coercion', () => {
  it('parses the decimal string the backend sends', () => {
    const parsed = serviceSchema.parse({
      id: 'ece21949-3995-4874-825d-38136d5a70db',
      slug: 'consultation-30-minutes',
      name: 'Consultation — 30 minutes',
      description: 'A first call to understand the matter and the way forward.',
      duration_minutes: 30,
      price_amount: '1500.00',
      currency: 'INR',
      requires_payment: true,
    })

    expect(parsed.price_amount).toBe(1500)
  })

  it('rejects a price that is not a number at all', () => {
    const result = serviceSchema.safeParse({
      id: 'x',
      slug: 'y',
      name: 'z',
      duration_minutes: 30,
      price_amount: 'not-a-price',
    })

    expect(result.success).toBe(false)
  })
})