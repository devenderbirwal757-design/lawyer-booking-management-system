'use client'

import { format } from 'date-fns'
import {
  CalendarPlusIcon,
  CheckCircle2Icon,
  FileTextIcon,
  LayoutDashboardIcon,
} from 'lucide-react'
import Link from 'next/link'

import { Button } from '@/components/ui/button'
import { Price } from '@/components/shared/price'
import { API_BASE_URL } from '@/lib/api/client'
import { siteConfig } from '@/lib/constants/site'
import { downloadIcs, toIcs } from '@/lib/utils/ics'

import type { Appointment } from '@/features/booking/schema'

interface ConfirmationStepProps {
  appointment: Appointment
}

export function ConfirmationStep({ appointment }: ConfirmationStepProps) {
  const service = appointment.service
  const durationMinutes = service.duration_minutes ?? 0
  const start = new Date(appointment.start_at)
  const end = new Date(start.getTime() + durationMinutes * 60_000)

  const addToCalendar = () => {
    downloadIcs(
      `consultation-${appointment.id}.ics`,
      toIcs({
        uid: appointment.id,
        start,
        end,
        summary: service.name ?? 'Consultation',
        description: 'Online consultation booking.',
        url: siteConfig.url,
      })
    )
  }

  return (
    <div className="flex flex-col items-center gap-6 text-center">
      <CheckCircle2Icon className="size-12 text-green-600" />

      <div className="flex flex-col gap-1">
        <h2 className="font-serif text-2xl tracking-tight">
          Booking confirmed
        </h2>
        <p className="text-sm text-muted-foreground">
          A confirmation has been sent to your mobile number.
        </p>
      </div>

      <dl className="grid w-full max-w-md grid-cols-1 gap-3 text-left sm:grid-cols-2">
        <div className="rounded-xl border border-border bg-card p-4">
          <dt className="text-xs text-muted-foreground">Booking ID</dt>
          <dd className="mt-0.5 font-mono text-sm">{appointment.id}</dd>
        </div>
        <div className="rounded-xl border border-border bg-card p-4">
          <dt className="text-xs text-muted-foreground">Service</dt>
          <dd className="mt-0.5 text-sm font-medium">{service.name}</dd>
        </div>
        <div className="rounded-xl border border-border bg-card p-4">
          <dt className="text-xs text-muted-foreground">Date &amp; time</dt>
          <dd className="mt-0.5 text-sm font-medium">
            {format(start, 'EEE, d MMM yyyy · h:mm a')}
          </dd>
        </div>
        <div className="rounded-xl border border-border bg-card p-4">
          <dt className="text-xs text-muted-foreground">Amount paid</dt>
          <dd className="mt-0.5 text-sm font-medium">
            <Price
              amount={service.price_amount ?? 0}
              currency={service.currency ?? 'INR'}
            />
          </dd>
        </div>
      </dl>

      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button variant="outline" onClick={addToCalendar}>
          <CalendarPlusIcon className="size-4" />
          Add to calendar
        </Button>
        <Button variant="outline" asChild>
          <a
            href={`${API_BASE_URL}/payments/${appointment.payment_order_id ?? ''}/receipt`}
            target="_blank"
            rel="noreferrer"
          >
            <FileTextIcon className="size-4" />
            Download receipt
          </a>
        </Button>
        <Button asChild>
          <Link href="/dashboard">
            <LayoutDashboardIcon className="size-4" />
            View in dashboard
          </Link>
        </Button>
      </div>
    </div>
  )
}
