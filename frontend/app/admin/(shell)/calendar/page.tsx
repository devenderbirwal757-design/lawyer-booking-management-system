'use client'

import {
  addDays,
  addMonths,
  endOfMonth,
  endOfWeek,
  format,
  isSameMonth,
  startOfMonth,
  startOfWeek,
  addWeeks,
  subMonths,
  subWeeks,
} from 'date-fns'
import { QueryError } from '@/components/shared/query-error'
import { ChevronLeftIcon, ChevronRightIcon } from 'lucide-react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useMemo, useState } from 'react'

import { BlockTimeDialog } from '@/components/admin/block-time-dialog'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { PageHeader } from '@/components/shared/page-header'
import { cn } from 'cn'
import { todayKey, toLocalDate, type DateKey } from '@/lib/utils/dates'

import { useAdminCalendar } from '@/features/admin/api'
import type { AdminCalendarEntry } from '@/features/admin/schema'

type CalendarView = 'month' | 'week' | 'day'

const VIEWS: { value: CalendarView; label: string }[] = [
  { value: 'month', label: 'Month' },
  { value: 'week', label: 'Week' },
  { value: 'day', label: 'Day' },
]

export default function AdminCalendarPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const view = (searchParams.get('view') as CalendarView) || 'month'
  const date = searchParams.get('date') ?? todayKey()
  const anchor = toLocalDate(date)

  const [blockTarget, setBlockTarget] = useState<{
    date: string
    startAt: string
  } | null>(null)

  const range = useMemo(() => {
    if (view === 'month') {
      return { from: startOfMonth(anchor), to: endOfMonth(anchor) }
    }
    if (view === 'week') {
      return { from: startOfWeek(anchor), to: endOfWeek(anchor) }
    }
    return { from: anchor, to: anchor }
  }, [view, anchor])

  const calendar = useAdminCalendar(
    view,
    format(range.from, 'yyyy-MM-dd'),
    format(range.to, 'yyyy-MM-dd')
  )

  const entries = calendar.data ?? []
  const navigate = (next: Date) => {
    const params = new URLSearchParams(searchParams.toString())
    params.set('date', format(next, 'yyyy-MM-dd'))
    router.replace(`?${params.toString()}`)
  }

  const setView = (next: CalendarView) => {
    const params = new URLSearchParams(searchParams.toString())
    params.set('view', next)
    router.replace(`?${params.toString()}`)
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Calendar"
        description="Month, week, and day views of the schedule."
        actions={
          <div className="flex items-center gap-2">
            <Select
              value={view}
              onValueChange={(value) => setView(value as CalendarView)}
            >
              <SelectTrigger className="h-9 w-32" aria-label="Calendar view">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {VIEWS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="icon"
              aria-label="Previous period"
              onClick={() =>
                navigate(
                  view === 'month'
                    ? subMonths(anchor, 1)
                    : view === 'week'
                      ? subWeeks(anchor, 1)
                      : addDays(anchor, -1)
                )
              }
            >
              <ChevronLeftIcon className="size-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              aria-label="Next period"
              onClick={() =>
                navigate(
                  view === 'month'
                    ? addMonths(anchor, 1)
                    : view === 'week'
                      ? addWeeks(anchor, 1)
                      : addDays(anchor, 1)
                )
              }
            >
              <ChevronRightIcon className="size-4" />
            </Button>
          </div>
        }
      />

      <p className="-mt-4 text-sm text-muted-foreground">
        {view === 'month'
          ? format(anchor, 'MMMM yyyy')
          : view === 'week'
            ? `${format(range.from, 'd MMM')} – ${format(range.to, 'd MMM yyyy')}`
            : format(anchor, 'EEEE, d MMMM yyyy')}
      </p>

      {calendar.isError ? (
        <QueryError
          error={calendar.error}
          onRetry={() => void calendar.refetch()}
          isRetrying={false}
        />
      ) : view === 'day' ? (
        <DayView
          date={date}
          entries={entries}
          loading={calendar.isLoading}
          onBlock={(target) => setBlockTarget(target)}
        />
      ) : (
        <GridView
          view={view}
          anchor={anchor}
          entries={entries}
          loading={calendar.isLoading}
          onSelectDate={(next) => {
            const params = new URLSearchParams(searchParams.toString())
            params.set('view', 'day')
            params.set('date', next)
            router.replace(`?${params.toString()}`)
          }}
        />
      )}

      {blockTarget ? (
        <BlockTimeDialog
          open
          date={blockTarget.date}
          startAt={blockTarget.startAt}
          onOpenChange={(open) => {
            if (!open) setBlockTarget(null)
          }}
        />
      ) : null}
    </div>
  )
}

function GridView({
  view,
  anchor,
  entries,
  loading,
  onSelectDate,
}: {
  view: 'month' | 'week'
  anchor: Date
  entries: AdminCalendarEntry[]
  loading: boolean
  onSelectDate: (date: DateKey) => void
}) {
  const counts = new Map<string, number>()
  entries.forEach((entry) => {
    const key = entry.date ?? entry.start_at?.slice(0, 10)
    if (!key) return
    counts.set(key, (counts.get(key) ?? 0) + (entry.count ?? 1))
  })

  const cells = view === 'month' ? monthCells(anchor) : weekCells(anchor)

  return (
    <div className="grid grid-cols-7 gap-px overflow-hidden rounded-xl border border-border bg-border">
      {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((label) => (
        <div
          key={label}
          className="bg-muted/50 px-2 py-1.5 text-center text-xs font-medium text-muted-foreground"
        >
          {label}
        </div>
      ))}
      {cells.map((cell) => {
        const key = format(cell, 'yyyy-MM-dd')
        const count = counts.get(key) ?? 0
        const outside = view === 'month' && !isSameMonth(cell, anchor)
        return (
          <button
            key={key}
            type="button"
            onClick={() => onSelectDate(key)}
            className={cn(
              'flex min-h-20 flex-col items-start gap-1 bg-card p-2 text-left transition-colors hover:bg-muted/50',
              outside && 'text-muted-foreground/40'
            )}
          >
            <span className="text-xs font-medium">{format(cell, 'd')}</span>
            {count > 0 && (
              <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary">
                {count} {count === 1 ? 'appt' : 'appts'}
              </span>
            )}
          </button>
        )
      })}
      {loading ? (
        <p className="col-span-7 bg-card p-4 text-center text-sm text-muted-foreground">
          Loading calendar…
        </p>
      ) : null}
    </div>
  )
}

function DayView({
  date,
  entries,
  loading,
  onBlock,
}: {
  date: string
  entries: AdminCalendarEntry[]
  loading: boolean
  onBlock: (target: { date: string; startAt: string }) => void
}) {
  const blocks = entries
    .filter((entry) => entry.start_at)
    .sort(
      (a, b) =>
        new Date(a.start_at as string).getTime() -
        new Date(b.start_at as string).getTime()
    )

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading schedule…</p>
  }

  if (!blocks.length) {
    return (
      <p className="text-sm text-muted-foreground">
        No slots on this day. Check availability settings or pick another date.
      </p>
    )
  }

  return (
    <ul className="flex flex-col gap-2">
      {blocks.map((block, index) => {
        const startAt = block.start_at as string
        const time = format(new Date(startAt), 'h:mm a')
        const common =
          'flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-4 py-3 text-sm'
        if (block.status === 'booked') {
          const label = block.customer?.name ?? 'Booked'
          return (
            <li key={`${startAt}-${index}`} className={common}>
              <span className="w-20 shrink-0 font-medium">{time}</span>
              <span className="flex-1 truncate">
                {block.appointment_id ? (
                  <Link
                    href={`/admin/appointments/${block.appointment_id}`}
                    className="font-medium hover:underline"
                  >
                    {label}
                  </Link>
                ) : (
                  <span className="font-medium">{label}</span>
                )}
                {block.service?.name ? (
                  <span className="ml-2 text-muted-foreground">
                    {block.service.name}
                  </span>
                ) : null}
              </span>
              <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900/30 dark:text-green-300">
                Booked
              </span>
            </li>
          )
        }
        if (block.status === 'blocked') {
          return (
            <li
              key={`${startAt}-${index}`}
              className={cn(common, 'bg-muted/40 text-muted-foreground')}
            >
              <span className="w-20 shrink-0 font-medium">{time}</span>
              <span className="flex-1">Blocked</span>
              <span className="rounded-full bg-border px-2 py-0.5 text-xs font-medium text-muted-foreground">
                Blocked
              </span>
            </li>
          )
        }
        return (
          <li key={`${startAt}-${index}`} className={common}>
            <span className="w-20 shrink-0 font-medium">{time}</span>
            <span className="flex-1 text-muted-foreground">Available</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onBlock({ date, startAt })}
            >
              Block time
            </Button>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/book">Book</Link>
            </Button>
          </li>
        )
      })}
    </ul>
  )
}

function monthCells(anchor: Date): Date[] {
  const start = startOfWeek(startOfMonth(anchor), { weekStartsOn: 1 })
  const end = endOfWeek(endOfMonth(anchor), { weekStartsOn: 1 })
  const cells: Date[] = []
  for (let d = start; d <= end; d = addDays(d, 1)) {
    cells.push(d)
  }
  return cells
}

function weekCells(anchor: Date): Date[] {
  const start = startOfWeek(anchor, { weekStartsOn: 1 })
  return Array.from({ length: 7 }, (_, i) => addDays(start, i))
}
