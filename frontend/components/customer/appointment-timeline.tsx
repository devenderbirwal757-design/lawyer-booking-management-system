import { format } from 'date-fns'

import { AppointmentStatusBadge } from '@/components/shared/status-badge'

import type { StatusHistoryEntry } from '@/features/portal/schema'

export function AppointmentTimeline({
  history,
}: {
  history: StatusHistoryEntry[]
}) {
  const ordered = [...history].sort(
    (a, b) =>
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  )

  if (!ordered.length) {
    return (
      <p className="text-sm text-muted-foreground">
        No status updates recorded yet.
      </p>
    )
  }

  return (
    <ol className="flex flex-col gap-5">
      {ordered.map((entry, index) => {
        const isLast = index === ordered.length - 1
        return (
          <li
            key={`${entry.created_at}-${index}`}
            className="relative flex gap-3"
          >
            {!isLast && (
              <span
                aria-hidden
                className="absolute top-7 left-[7px] h-full w-px bg-border"
              />
            )}
            <span aria-hidden className={cnDot(isLast)} />
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <div className="flex flex-wrap items-center gap-2">
                <AppointmentStatusBadge status={entry.to_status} />
                <span className="text-xs text-muted-foreground">
                  {format(new Date(entry.created_at), 'd MMM yyyy, h:mm a')}
                </span>
              </div>
              {entry.note ? (
                <p className="text-sm text-muted-foreground">{entry.note}</p>
              ) : null}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

function cnDot(isLast: boolean): string {
  return [
    'mt-1.5 size-3.5 shrink-0 rounded-full border-2',
    isLast ? 'bg-primary border-primary' : 'bg-background border-primary/50',
  ].join(' ')
}
