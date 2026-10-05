import { addDays, format, parse, parseISO, startOfToday } from 'date-fns'

export type DateKey = string

export const todayKey = (): DateKey => format(startOfToday(), 'yyyy-MM-dd')

export function toLocalDate(dateKey: DateKey): Date {
  return parseISO(dateKey)
}

export const addDaysKey = (dateKey: DateKey, days: number): DateKey =>
  format(addDays(parseISO(dateKey), days), 'yyyy-MM-dd')

export const monthKey = (dateKey: DateKey): string => dateKey.slice(0, 7)

export const displayDate = (dateKey: DateKey): string =>
  format(parseISO(dateKey), 'EEE, d MMM')

export const numericDate = (dateKey: DateKey): string =>
  format(parseISO(dateKey), 'd MMM')

const TIME_PATTERN = /^\d{1,2}:\d{2}(:\d{2})?$/

/**
 * Resolve a slot to a `Date`, or `null` when the value is not a time at all.
 *
 * Two shapes reach this module. The API sends full ISO timestamps
 * (`2026-10-05T10:00:00+00:00`), while the wizard also passes a bare
 * `HH:mm`/`HH:mm:ss` label. Splitting an ISO string on `:` yields `"2026-10-05T10"`
 * for the hour, which is `NaN`, so an unguarded parse both printed the raw
 * timestamp to the customer and filed every slot under "Evening".
 */
function slotDate(slotLabel: string): Date | null {
  const raw = slotLabel.trim()
  if (TIME_PATTERN.test(raw)) {
    return raw.split(':')[2] ? parse(raw, 'HH:mm:ss', new Date()) : parse(raw, 'HH:mm', new Date())
  }
  const iso = parseISO(raw)
  return Number.isNaN(iso.getTime()) ? null : iso
}

export function displaySlotTime(slotLabel: string): string {
  const date = slotDate(slotLabel)
  // Unparseable values are shown verbatim rather than hidden, so a contract
  // change shows up in the UI instead of silently blanking the slot list.
  return date ? format(date, 'h:mm a') : slotLabel.trim()
}

export function groupByTimeOfDay(
  slots: string[]
): Array<{ key: string; label: string; slots: string[] }> {
  const groups: Array<{ key: string; label: string; slots: string[] }> = [
    { key: 'morning', label: 'Morning', slots: [] },
    { key: 'afternoon', label: 'Afternoon', slots: [] },
    { key: 'evening', label: 'Evening', slots: [] },
  ]

  for (const slot of slots) {
    const date = slotDate(slot)
    const hour = date ? date.getHours() : Number.NaN
    if (Number.isNaN(hour)) {
      groups[2].slots.push(slot)
    } else if (hour < 12) {
      groups[0].slots.push(slot)
    } else if (hour < 17) {
      groups[1].slots.push(slot)
    } else {
      groups[2].slots.push(slot)
    }
  }

  return groups.filter((group) => group.slots.length > 0)
}

export function slotToIso(dateKey: DateKey, slotLabel: string): string {
  if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(slotLabel)) {
    return new Date(`${dateKey}T${slotLabel}`).toISOString()
  }
  return slotLabel
}
