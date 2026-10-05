import { describe, expect, it } from 'vitest'

import { ApiError, parseApiErrorBody } from '@/lib/api/error'

describe('parseApiErrorBody', () => {
  it('parses the RFC-7807-ish error envelope', () => {
    const err = parseApiErrorBody(409, {
      error: {
        code: 'SLOT_UNAVAILABLE',
        message: 'That time was just taken.',
      },
    })

    expect(err).toBeInstanceOf(ApiError)
    expect(err?.status).toBe(409)
    expect(err?.code).toBe('SLOT_UNAVAILABLE')
    expect(err?.isSlotUnavailable).toBe(true)
  })

  it('surfaces structured details when present', () => {
    const err = parseApiErrorBody(400, {
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Invalid phone number.',
        details: { phone: ['Enter a valid 10-digit mobile number.'] },
      },
    })

    expect(err?.code).toBe('VALIDATION_ERROR')
    expect(err?.details).toEqual({
      phone: ['Enter a valid 10-digit mobile number.'],
    })
  })

  it('returns null for success-like payloads', () => {
    expect(parseApiErrorBody(200, { data: [] })).toBeNull()
  })

  it('returns null for non-object bodies', () => {
    expect(parseApiErrorBody(500, 'boom')).toBeNull()
    expect(parseApiErrorBody(500, null)).toBeNull()
  })
})
