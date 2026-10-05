import { describe, expect, it } from 'vitest'

import { formatDuration, formatMoney } from '@/lib/utils/money'

describe('formatMoney', () => {
  it('formats INR with Indian grouping', () => {
    expect(formatMoney(500)).toBe('₹500')
    expect(formatMoney(12500)).toBe('₹12,500')
    expect(formatMoney(125000)).toBe('₹1,25,000')
  })

  it('includes decimals when present', () => {
    expect(formatMoney(499.5)).toBe('₹499.5')
  })

  it('supports other currencies', () => {
    expect(formatMoney(99, 'USD')).toContain('$')
    expect(formatMoney(99, 'USD')).toContain('99')
  })

  it('rejects non-finite amounts', () => {
    expect(() => formatMoney(Number.NaN)).toThrow(TypeError)
    expect(() => formatMoney(Number.POSITIVE_INFINITY)).toThrow(TypeError)
  })
})

describe('formatDuration', () => {
  it('formats under an hour as minutes', () => {
    expect(formatDuration(30)).toBe('30 min')
    expect(formatDuration(45)).toBe('45 min')
  })

  it('formats whole hours', () => {
    expect(formatDuration(60)).toBe('1 hr')
  })

  it('formats hours and minutes', () => {
    expect(formatDuration(90)).toBe('1 hr 30 min')
  })
})
