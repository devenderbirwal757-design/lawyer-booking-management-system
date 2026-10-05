import { describe, expect, it } from 'vitest'

import { formatCountdown } from '@/lib/hooks/use-countdown'

describe('formatCountdown', () => {
  it('formats 5 minutes as a timer', () => {
    expect(formatCountdown(300)).toBe('5:00')
  })

  it('pads seconds with a leading zero', () => {
    expect(formatCountdown(65)).toBe('1:05')
    expect(formatCountdown(9)).toBe('0:09')
  })

  it('handles zero', () => {
    expect(formatCountdown(0)).toBe('0:00')
  })
})
