import { describe, expect, it } from 'vitest'

import { stripLeading0, toE164 } from '@/lib/utils/phone'

describe('toE164', () => {
  it('prefixes a 10-digit number with the country code', () => {
    expect(toE164('9876543210')).toBe('+919876543210')
  })

  it('rejects invalid numbers', () => {
    expect(() => toE164('12345')).toThrow()
    expect(() => toE164('5123456789')).toThrow()
  })
})

describe('stripLeading0', () => {
  it('removes a leading zero', () => {
    expect(stripLeading0('09876543210')).toBe('9876543210')
  })

  it('leaves other numbers untouched', () => {
    expect(stripLeading0('9876543210')).toBe('9876543210')
  })
})
