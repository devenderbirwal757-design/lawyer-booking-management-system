'use client'

import { format } from 'date-fns'
import {
  AlertCircleIcon,
  ArrowLeftIcon,
  CalendarDaysIcon,
  FileTextIcon,
} from 'lucide-react'
import Link from 'next/link'
import { use, useState } from 'react'

import { AppointmentTimeline } from '@/components/customer/appointment-timeline'
import { CancelBookingDialog } from '@/components/customer/cancel-booking-dialog'
import { RescheduleDialog } from '@/components/customer/reschedule-dialog'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { API_BASE_URL } from '@/lib/api/client'
import { toApiError } from '@/lib/api/error'
import { Price } from '@/components/shared/price'
import { AppointmentStatusBadge } from '@/components/shared/status-badge'

import { useMeAppointment } from '@/features/portal/api'

export default function BookingDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [confirmReschedule, setConfirmReschedule] = useState(false)

  const appointment = useMeAppointment(id)

  if (appointment.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full rounded-2xl" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
    )
  }

  if (appointment.isError || !appointment.data) {
    return (
      <div className="flex flex-col gap-4">
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Could not load this booking</AlertTitle>
          <AlertDescription>
            {appointment.isError
              ? toApiError(appointment.error).message
              : 'This booking could not be found.'}
          </AlertDescription>
        </Alert>
        <Button variant="outline" asChild className="w-fit">
          <Link href="/dashboard">
            <ArrowLeftIcon className="size-4" />
            Back to dashboard
          </Link>
        </Button>
      </div>
    )
  }

  const data = appointment.data
  const service = data.service
  const start = new Date(data.start_at)
  const hasPaid =
    data.payment?.status === 'SUCCESS' || Boolean(data.payment_order_id)
  const receiptId =
    data.payment_order_id ??
    data.payment?.payment_order_id ??
    data.payment?.order_id
  const canManage =
    data.status === 'CONFIRMED' || data.status === 'PENDING_PAYMENT'

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link href="/dashboard" className="hover:text-foreground">
              Dashboard
            </Link>
            <span>/</span>
            <span>Booking</span>
          </p>
          <h1 className="font-serif text-2xl font-semibold tracking-tight">
            {service.name ?? 'Consultation'}
          </h1>
        </div>
        <AppointmentStatusBadge status={data.status} />
      </div>

      <dl className="grid gap-3 rounded-2xl border border-border bg-card p-5 sm:grid-cols-2">
        <Detail label="Booking ID" mono>
          {data.id}
        </Detail>
        <Detail label="Service">{service.name ?? 'Consultation'}</Detail>
        <Detail label="Date">
          <span className="inline-flex items-center gap-1.5">
            <CalendarDaysIcon className="size-4 text-muted-foreground" />
            {format(start, 'EEE, d MMM yyyy')}
          </span>
        </Detail>
        <Detail label="Time">{format(start, 'h:mm a')}</Detail>
        <Detail label="Amount">
          {typeof service.price_amount === 'number' ? (
            <Price
              amount={service.price_amount}
              currency={service.currency ?? 'INR'}
              className="font-semibold"
            />
          ) : (
            '—'
          )}
        </Detail>
        <Detail label="Payment">
          {data.payment?.status
            ? data.payment.status
            : hasPaid
              ? 'Paid'
              : 'Pending'}
        </Detail>
      </dl>

      {canManage && (
        <div className="flex flex-wrap gap-3">
          <Button variant="outline" onClick={() => setConfirmReschedule(true)}>
            Reschedule
          </Button>
          <Button variant="destructive" onClick={() => setConfirmCancel(true)}>
            Cancel booking
          </Button>
        </div>
      )}

      {receiptId && (
        <a
          href={`${API_BASE_URL}/payments/${receiptId}/receipt`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex w-fit items-center gap-2 text-sm font-medium text-primary"
        >
          <FileTextIcon className="size-4" />
          Download receipt
        </a>
      )}

      <section className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-5">
        <h2 className="text-base font-semibold">Status history</h2>
        <AppointmentTimeline history={data.status_history ?? []} />
      </section>

      {canManage && data && (
        <>
          <CancelBookingDialog
            appointment={data}
            open={confirmCancel}
            onOpenChange={setConfirmCancel}
          />
          <RescheduleDialog
            appointment={data}
            open={confirmReschedule}
            onOpenChange={setConfirmReschedule}
          />
        </>
      )}
    </div>
  )
}

function Detail({
  label,
  children,
  mono,
}: {
  label: string
  children: React.ReactNode
  mono?: boolean
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={mono ? 'font-mono text-sm' : 'text-sm'}>{children}</dd>
    </div>
  )
}
