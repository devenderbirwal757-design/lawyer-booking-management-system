'use client'

import { format } from 'date-fns'
import { QueryError } from '@/components/shared/query-error'
import { ArrowLeftIcon } from 'lucide-react'
import Link from 'next/link'
import { notFound, useParams } from 'next/navigation'

import { AppointmentActions } from '@/components/admin/appointment-actions'
import { AppointmentTimeline } from '@/components/customer/appointment-timeline'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { PageHeader } from '@/components/shared/page-header'
import { Price } from '@/components/shared/price'
import {
  AppointmentStatusBadge,
  PaymentStatusBadge,
} from '@/components/shared/status-badge'
import { Skeleton } from '@/components/ui/skeleton'
import { toApiError, ErrorCodes } from '@/lib/api/error'

import {
  useAdminAppointmentDetail,
  useAdminAuditLogs,
} from '@/features/admin/api'

export default function AdminAppointmentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const appointment = useAdminAppointmentDetail(id)
  const audit = useAdminAuditLogs({
    entity_type: 'appointment',
    entity_id: id,
  })

  if (appointment.isError) {
    const error = toApiError(appointment.error)
    if (error.status === 404 || error.code === ErrorCodes.notFound) {
      notFound()
    }
    return (
      <QueryError
        error={appointment.error}
        onRetry={() => void appointment.refetch()}
        isRetrying={appointment.isFetching}
      />
    )
  }

  const row = appointment.data

  return (
    <div className="flex flex-col gap-6">
      <Button variant="ghost" size="sm" asChild className="-mx-3 w-fit">
        <Link href="/admin/appointments">
          <ArrowLeftIcon className="size-4" /> Appointments
        </Link>
      </Button>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-2">
          <PageHeader
            title={row?.customer?.name ?? row?.customer?.phone ?? 'Appointment'}
            description={
              row
                ? `${format(new Date(row.start_at), 'EEEE, d MMMM yyyy')} at ${format(new Date(row.start_at), 'h:mm a')}`
                : 'Loading…'
            }
          />
          <div className="flex items-center gap-2">
            {row ? <AppointmentStatusBadge status={row.status} /> : null}
            {row?.payment?.status ? (
              <PaymentStatusBadge status={row.payment?.status} />
            ) : null}
          </div>
        </div>
        {row ? <AppointmentActions appointment={row} /> : null}
      </div>

      {!row ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-16 w-full rounded-xl" />
          <Skeleton className="h-16 w-full rounded-xl" />
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Details</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              <Row label="Service">{row.service?.name ?? '—'}</Row>
              <Row label="Phone">{row.customer?.phone ?? '—'}</Row>
              <Row label="Email">{row.customer?.email ?? '—'}</Row>
              <Row label="Duration">
                {row.service?.duration_minutes
                  ? `${row.service.duration_minutes} minutes`
                  : '—'}
              </Row>
              <Row label="Price">
                {row.service?.price != null ? (
                  <Price amount={row.service.price} />
                ) : (
                  '—'
                )}
              </Row>
              <Row label="Booked">
                {row.created_at
                  ? format(new Date(row.created_at), 'd MMM yyyy, h:mm a')
                  : '—'}
              </Row>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Status history</CardTitle>
            </CardHeader>
            <CardContent>
              <AppointmentTimeline history={row.status_history ?? []} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Recent activity</CardTitle>
            </CardHeader>
            <CardContent>
              {audit.isError ? (
                <p className="text-sm text-muted-foreground">
                  Audit trail unavailable.
                </p>
              ) : (audit.data?.results ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No recent activity recorded.
                </p>
              ) : (
                <ol className="flex flex-col gap-3">
                  {(audit.data?.results ?? []).slice(0, 8).map((entry) => (
                    <li key={entry.id} className="flex flex-col gap-0.5">
                      <span className="text-sm font-medium capitalize">
                        {entry.action.replace(/_/g, ' ')}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {entry.created_at
                          ? format(new Date(entry.created_at), 'd MMM, h:mm a')
                          : '—'}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

function Row({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{children}</span>
    </div>
  )
}
