'use client'

import { format } from 'date-fns'
import { QueryError } from '@/components/shared/query-error'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'

import { AppointmentFilterBar } from '@/components/admin/filter-bar'
import { AppointmentActions } from '@/components/admin/appointment-actions'
import { Pagination } from '@/components/admin/pagination'
import { DataTable } from '@/components/shared/data-table'
import { PageHeader } from '@/components/shared/page-header'
import {
  AppointmentStatusBadge,
  PaymentStatusBadge,
} from '@/components/shared/status-badge'
import { todayKey } from '@/lib/utils/dates'

import {
  useAdminAppointments,
  type AdminAppointmentsFilters,
} from '@/features/admin/api'

export default function AdminAppointmentsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()

  const filters: AdminAppointmentsFilters = {
    date: searchParams.get('date') ?? undefined,
    status: searchParams.get('status') ?? undefined,
    payment_status: searchParams.get('payment_status') ?? undefined,
    q: searchParams.get('q') ?? undefined,
    page: searchParams.get('page')
      ? Number(searchParams.get('page'))
      : undefined,
  }

  const appointments = useAdminAppointments(filters)

  const setPage = (page: number) => {
    const params = new URLSearchParams(searchParams.toString())
    if (page > 1) {
      params.set('page', String(page))
    } else {
      params.delete('page')
    }
    const query = params.toString()
    router.replace(query ? `?${query}` : '/admin/appointments')
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Appointments"
        description="Search, filter, and manage every booking."
      />

      <AppointmentFilterBar
        defaults={{ date: todayKey(), status: '', payment_status: '' }}
        onSearch={(q) => {
          const params = new URLSearchParams(searchParams.toString())
          if (q) {
            params.set('q', q)
          } else {
            params.delete('q')
          }
          params.delete('page')
          const query = params.toString()
          router.replace(query ? `?${query}` : '/admin/appointments')
        }}
      />

      {appointments.isError ? (
        <QueryError
          error={appointments.error}
          onRetry={() => void appointments.refetch()}
          isRetrying={false}
        />
      ) : (
        <>
          <DataTable
            data={appointments.data?.results ?? []}
            keyFor={(row) => row.id}
            loading={appointments.isLoading}
            emptyTitle="No appointments match these filters"
            emptyDescription="Adjust the date, statuses, or search to see more results."
            columns={[
              {
                header: 'Date & time',
                cell: (row) => (
                  <Link
                    href={`/admin/appointments/${row.id}`}
                    className="whitespace-nowrap font-medium hover:underline"
                  >
                    {format(new Date(row.start_at), 'MMM d, yyyy · h:mm a')}
                  </Link>
                ),
                headClassName: 'w-44',
              },
              {
                header: 'Client',
                cell: (row) => (
                  <span className="font-medium">
                    {row.customer?.name ?? row.customer?.phone ?? '—'}
                  </span>
                ),
              },
              {
                header: 'Service',
                cell: (row) => (
                  <span className="text-muted-foreground">
                    {row.service?.name ?? '—'}
                  </span>
                ),
              },
              {
                header: 'Payment',
                cell: (row) => (
                  <PaymentStatusBadge status={row.payment?.status} />
                ),
              },
              {
                header: 'Status',
                cell: (row) => <AppointmentStatusBadge status={row.status} />,
              },
              {
                header: <span className="sr-only">Actions</span>,
                cell: (row) => <AppointmentActions appointment={row} />,
                className: 'w-12 text-right',
              },
            ]}
          />
          <Pagination
            hasPrevious={Boolean(appointments.data?.previous)}
            hasNext={Boolean(appointments.data?.next)}
            disabled={appointments.isFetching}
            onPrevious={() => setPage((filters.page ?? 1) - 1)}
            onNext={() => setPage((filters.page ?? 1) + 1)}
          />
        </>
      )}
    </div>
  )
}
