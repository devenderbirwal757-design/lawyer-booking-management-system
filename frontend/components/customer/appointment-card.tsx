import { format } from 'date-fns'
import { CalendarDaysIcon, ChevronRightIcon } from 'lucide-react'
import Link from 'next/link'

import { cn } from 'cn'

import { Price } from '@/components/shared/price'
import { AppointmentStatusBadge } from '@/components/shared/status-badge'

import type { AppointmentDetail } from '@/features/portal/schema'

export function AppointmentCard({
  appointment,
  className,
}: {
  appointment: AppointmentDetail
  className?: string
}) {
  const service = appointment.service
  const start = new Date(appointment.start_at)

  return (
    <Link
      href={`/bookings/${appointment.id}`}
      className={cn(
        'group flex items-center gap-4 rounded-xl border border-border bg-card p-4 transition-colors hover:border-primary/40',
        className
      )}
    >
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium">
            {service.name ?? 'Consultation'}
          </span>
          <AppointmentStatusBadge status={appointment.status} />
        </div>
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <CalendarDaysIcon className="size-4" />
          <span>{format(start, 'EEE, d MMM yyyy · h:mm a')}</span>
        </div>
        <span className="font-mono text-xs text-muted-foreground">
          {appointment.id}
        </span>
      </div>

      <div className="flex shrink-0 items-center gap-3">
        {typeof service.price_amount === 'number' ? (
          <Price
            amount={service.price_amount}
            currency={service.currency ?? 'INR'}
            className="font-semibold"
          />
        ) : null}
        <ChevronRightIcon className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
      </div>
    </Link>
  )
}
