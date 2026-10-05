import { describe, expect, it } from 'vitest'

import {
  serviceListPageSchema,
  serviceSchema,
} from '@/features/services/schema'

/**
 * Regression coverage for the services contract.
 *
 * The backend serialises `price_amount` as a decimal *string* (`"1500.00"`),
 * not a number. A bare `api.get<Service[]>` assertion used to hand that string
 * straight to `formatMoney`, which threw on `Number.isFinite` and crashed the
 * whole booking page into its error boundary. The schema has to coerce.
 *
 * Payload below is verbatim from `GET /api/v1/services/?status=active`.
 */
const rawService = {
  id: 'ece21949-3995-4874-825d-38136d5a70db',
  slug: 'consultation-30-minutes',
  name: 'Consultation — 30 minutes',
  description: 'A first call to understand the matter and the way forward.',
  duration_minutes: 30,
  buffer_before_minutes: 0,
  buffer_after_minutes: 5,
  price_amount: '1500.00',
  price: '₹1500',
  currency: 'INR',
  requires_payment: true,
}

describe('serviceSchema', () => {
  it('coerces the decimal string price to a finite number', () => {
    const parsed = serviceSchema.parse(rawService)
    expect(parsed.price_amount).toBe(1500)
    expect(Number.isFinite(parsed.price_amount)).toBe(true)
  })

  it('defaults the optional fields the backend omits', () => {
    const parsed = serviceSchema.parse(rawService)
    expect(parsed.status).toBe('active')
    expect(parsed.currency).toBe('INR')
  })

  it('rejects a missing price', () => {
    const missingPrice: Record<string, unknown> = { ...rawService }
    delete missingPrice.price_amount
    expect(serviceSchema.safeParse(missingPrice).success).toBe(false)
  })
})

describe('serviceListPageSchema', () => {
  it('parses the paginated envelope the backend actually returns', () => {
    const parsed = serviceListPageSchema.parse({
      count: 1,
      page: 1,
      page_size: 20,
      num_pages: 1,
      next: null,
      previous: null,
      results: [rawService],
    })
    expect(parsed.results).toHaveLength(1)
    expect(parsed.results[0].price_amount).toBe(1500)
  })
})