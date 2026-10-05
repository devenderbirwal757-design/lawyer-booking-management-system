import { describe, expect, it } from 'vitest'

import { displaySlotTime, groupByTimeOfDay } from '@/lib/utils/dates'

/**
 * The availability API returns full ISO timestamps
 * (`2026-10-05T10:00:00+00:00`), not the bare `HH:mm` labels these helpers
 * were written for. Splitting an ISO string on `:` puts `2026-10-05T10` where
 * the hour is expected, which is `NaN` - so the customer saw raw timestamps in
 * the slot list and every slot was filed under "Evening".
 *
 * Both shapes still have to work: the wizard also passes bare time labels.
 */
describe('displaySlotTime', () => {
  it('formats a bare HH:mm label', () => {
    expect(displaySlotTime('14:30')).toMatch(/^2:30\s?PM$/i)
  })

  it('formats a bare HH:mm:ss label', () => {
    expect(displaySlotTime('09:05:00')).toMatch(/^9:05\s?AM$/i)
  })

  it('formats a full ISO timestamp instead of echoing it', () => {
    const formatted = displaySlotTime('2026-10-05T10:00:00+00:00')
    expect(formatted).toMatch(/^\d{1,2}:\d{2}\s?(am|pm)$/i)
    expect(formatted).not.toContain('2026-10-05')
  })

  it('returns unparseable input verbatim rather than blanking it', () => {
    expect(displaySlotTime('whenever')).toBe('whenever')
  })
})

describe('groupByTimeOfDay', () => {
  it('buckets ISO timestamps by local hour instead of NaN', () => {
    const groups = groupByTimeOfDay([
      '2026-10-05T04:00:00+00:00', // 00:00 UTC -> morning in most zones, but the
      // grouping must at least be decided by a real number rather than NaN.
      '2026-10-05T16:00:00+00:00',
    ])

    const labels = groups.map((group) => group.label)
    expect(labels.length).toBeGreaterThan(0)
    expect(labels.every((label) => ['Morning', 'Afternoon', 'Evening'].includes(label)))
      .toBe(true)
  })

  it('keeps every slot it was given', () => {
    const slots = ['09:00', '13:00', '19:00']
    const grouped = groupByTimeOfDay(slots).flatMap((group) => group.slots)
    expect(grouped.sort()).toEqual([...slots].sort())
  })

  it('still buckets bare labels correctly', () => {
    const groups = groupByTimeOfDay(['08:00', '13:00', '20:00'])
    expect(groups.map((group) => group.key)).toEqual([
      'morning',
      'afternoon',
      'evening',
    ])
  })
})