import { describe, expect, it } from 'vitest'

import { toIcs } from '@/lib/utils/ics'

describe('toIcs', () => {
  it('emits a VCALENDAR with UTC timestamps', () => {
    const start = new Date('2026-10-05T10:00:00Z')
    const end = new Date('2026-10-05T10:30:00Z')

    const ics = toIcs({
      uid: 'abc-123',
      start,
      end,
      summary: 'Consultation',
    })

    expect(ics).toContain('BEGIN:VCALENDAR')
    expect(ics).toContain('END:VCALENDAR')
    expect(ics).toContain('BEGIN:VEVENT')
    expect(ics).toContain('UID:abc-123')
    expect(ics).toContain('DTSTART:20261005T100000Z')
    expect(ics).toContain('DTEND:20261005T103000Z')
    expect(ics).toContain('SUMMARY:Consultation')
    expect(ics.endsWith('\r\n')).toBe(true)
  })

  it('escapes syntax-significant characters', () => {
    const ics = toIcs({
      uid: '1',
      start: new Date('2026-10-05T10:00:00Z'),
      end: new Date('2026-10-05T10:30:00Z'),
      summary: 'Consultation, urgent; LN (test)',
    })

    expect(ics).toContain('SUMMARY:Consultation\\, urgent\\; LN (test)')
  })
})
