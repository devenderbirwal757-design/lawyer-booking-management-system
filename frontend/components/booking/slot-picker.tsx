import { addMonths, format, getDaysInMonth, startOfMonth } from 'date-fns'
import {
  CalendarDaysIcon,
  CalendarPlusIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClockIcon,
} from 'lucide-react'
import * as React from 'react'

import { cn } from 'cn'

import {
  addDaysKey,
  displayDate,
  displaySlotTime,
  groupByTimeOfDay,
  numericDate,
  todayKey,
  type DateKey,
} from '@/lib/utils/dates'

import {
  useAvailabilityDates,
  useAvailabilitySlots,
} from '@/features/booking/api'

interface SlotPickerProps {
  serviceId: string
  date: DateKey | null
  startAt: string | null
  onSelect: (date: DateKey, startAt: string, slotLabel: string) => void
}

const STRIP_DAYS = 14

export function SlotPicker({
  serviceId,
  date,
  startAt,
  onSelect,
}: SlotPickerProps) {
  const today = todayKey()
  const selectedMonth = (date ?? today).slice(0, 7)
  const datesQuery = useAvailabilityDates(serviceId, selectedMonth)

  const availableDates = new Set<string>()
  if (datesQuery.data) {
    const raw = Array.isArray(datesQuery.data)
      ? datesQuery.data
      : datesQuery.data.dates
    raw.forEach((item) => availableDates.add(item))
  }

  const stripDays = Array.from({ length: STRIP_DAYS }, (_, i) =>
    addDaysKey(today, i)
  )

  return (
    <div className="flex flex-col gap-6">
      <div role="radiogroup" aria-label="Choose a date" className="relative">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {stripDays.map((day) => {
            const selected = day === date
            const hasAvailability = availableDates.has(day)
            return (
              <button
                key={day}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => onSelect(day, '', '')}
                className={cn(
                  'flex min-w-16 shrink-0 flex-col items-center gap-1 rounded-xl border px-2 py-2 text-sm transition-colors',
                  selected
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border bg-card hover:border-primary/50',
                  !hasAvailability && !selected && 'opacity-60'
                )}
              >
                <span className="text-xs opacity-80">
                  {format(toLocalDate(day), 'EEE')}
                </span>
                <span className="text-lg font-semibold leading-none">
                  {format(toLocalDate(day), 'd')}
                </span>
                <span
                  aria-hidden
                  className={cn(
                    'size-1 rounded-full',
                    hasAvailability
                      ? selected
                        ? 'bg-primary-foreground'
                        : 'bg-primary'
                      : 'bg-transparent'
                  )}
                />
              </button>
            )
          })}
        </div>
      </div>

      <MonthGrid
        month={selectedMonth}
        selectedDate={date}
        availableDates={availableDates}
        onSelectDate={(day) => onSelect(day, '', '')}
      />

      {date && (
        <ScheduleForDate
          key={date}
          serviceId={serviceId}
          date={date}
          startAt={startAt}
          onSelect={onSelect}
        />
      )}
    </div>
  )
}

function toLocalDate(dateKey: DateKey): Date {
  return new Date(`${dateKey}T00:00:00`)
}

const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']

function MonthGrid({
  month,
  selectedDate,
  availableDates,
  onSelectDate,
}: {
  month: string
  selectedDate: DateKey | null
  availableDates: Set<string>
  onSelectDate: (date: DateKey) => void
}) {
  const [viewing, setViewing] = React.useState(month)
  React.useEffect(() => setViewing(month), [month])

  const firstDay = startOfMonth(new Date(`${viewing}-01T00:00:00`))
  const daysInMonth = getDaysInMonth(firstDay)
  const monthStartOffset = (firstDay.getDay() + 6) % 7
  const days = Array.from(
    { length: daysInMonth },
    (_, i) => `${viewing}-${String(i + 1).padStart(2, '0')}`
  )

  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium">
          {format(firstDay, 'MMMM yyyy')}
        </span>
        <div className="flex gap-1">
          <button
            type="button"
            aria-label="Previous month"
            onClick={() =>
              setViewing(format(addMonths(firstDay, -1), 'yyyy-MM'))
            }
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted"
          >
            <ChevronLeftIcon className="size-4" />
          </button>
          <button
            type="button"
            aria-label="Next month"
            onClick={() =>
              setViewing(format(addMonths(firstDay, 1), 'yyyy-MM'))
            }
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted"
          >
            <ChevronRightIcon className="size-4" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-1 text-center text-xs text-muted-foreground">
        {WEEKDAYS.map((day) => (
          <span key={day} className="py-1">
            {day}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: monthStartOffset }).map((_, i) => (
          <span key={`empty-${i}`} />
        ))}
        {days.map((day) => {
          const selected = day === selectedDate
          const isToday = day === todayKey()
          const hasAvailability = availableDates.has(day)
          return (
            <button
              key={day}
              type="button"
              onClick={() => onSelectDate(day)}
              aria-pressed={selected}
              title={hasAvailability ? 'Available' : undefined}
              className={cn(
                'flex aspect-square flex-col items-center justify-center gap-0.5 rounded-lg text-sm transition-colors',
                selected
                  ? 'bg-primary text-primary-foreground'
                  : 'hover:bg-muted',
                isToday && !selected && 'font-semibold text-primary'
              )}
            >
              <span>{Number(day.slice(8))}</span>
              {hasAvailability && (
                <span
                  aria-hidden
                  className={cn(
                    'size-1 rounded-full',
                    selected ? 'bg-primary-foreground' : 'bg-primary'
                  )}
                />
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function ScheduleForDate({
  serviceId,
  date,
  startAt,
  onSelect,
}: {
  serviceId: string
  date: DateKey
  startAt: string | null
  onSelect: (date: DateKey, startAt: string, slotLabel: string) => void
}) {
  const slotsQuery = useAvailabilitySlots(serviceId, date)

  if (slotsQuery.isLoading) {
    return (
      <div className="flex flex-col gap-2">
        <div className="h-5 w-40 animate-pulse rounded bg-muted" />
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      </div>
    )
  }

  const groups = groupByTimeOfDay(slotsQuery.data ?? [])

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <CalendarDaysIcon className="size-4" />
        {displayDate(date)}
      </div>

      {slotsQuery.data?.length ? (
        <>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
            <ClockIcon className="size-4" />
            Available times
          </div>
          <SlotGrid
            slots={slotsQuery.data}
            groups={groups}
            selected={startAt}
            onSelect={(startAt) => onSelect(date, startAt, startAt)}
          />
        </>
      ) : (
        <EmptySlots date={date} />
      )}
    </div>
  )
}

function SlotGrid({
  slots,
  groups,
  selected,
  onSelect,
}: {
  slots: string[]
  groups: Array<{ key: string; label: string; slots: string[] }>
  selected: string | null
  onSelect: (startAt: string) => void
}) {
  const buttonsRef = React.useRef<Array<HTMLButtonElement | null>>([])

  const handleKeyDown = (
    e: React.KeyboardEvent<HTMLButtonElement>,
    index: number
  ) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') {
      return
    }
    e.preventDefault()
    const offset = e.key === 'ArrowRight' ? 1 : -1
    const nextIndex = index + offset
    if (nextIndex >= 0 && nextIndex < slots.length) {
      buttonsRef.current[nextIndex]?.focus()
    }
  }

  if (!groups.length) {
    return null
  }

  // Roving tabindex: the selected slot is the entry point, or the first slot
  // when nothing is selected yet, so the group is always keyboard reachable.
  const focusableIndex = selected ? Math.max(slots.indexOf(selected), 0) : 0

  return (
    <div
      role="radiogroup"
      aria-label="Choose a time"
      className="flex flex-col gap-4"
    >
      {groups.map((group) => (
        <div key={group.key} className="flex flex-col gap-2">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {group.label}
          </h3>
          <div className="flex flex-wrap gap-2">
            {group.slots.map((slot) => {
              const index = slots.indexOf(slot)
              const isSelected = slot === selected
              return (
                <button
                  key={slot}
                  type="button"
                  role="radio"
                  aria-checked={isSelected}
                  ref={(el) => {
                    buttonsRef.current[index] = el
                  }}
                  onKeyDown={(e) => handleKeyDown(e, index)}
                  tabIndex={index === focusableIndex ? 0 : -1}
                  onClick={() => onSelect(slot)}
                  className={cn(
                    'rounded-lg border px-3 py-2 text-sm font-medium transition-colors',
                    isSelected
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border bg-card hover:border-primary/50'
                  )}
                >
                  {displaySlotTime(slot)}
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

function EmptySlots({ date }: { date: DateKey }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-dashed border-border px-4 py-6 text-center">
      <CalendarPlusIcon className="mx-auto mb-1 size-5 text-muted-foreground" />
      <p className="text-sm font-medium">
        {numericDate(date)} is fully booked.
      </p>
      <p className="text-sm text-muted-foreground">
        Pick another day to see the next available times.
      </p>
    </div>
  )
}
