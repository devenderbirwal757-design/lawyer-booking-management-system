'use client'

import { format } from 'date-fns'
import { QueryError } from '@/components/shared/query-error'
import {
  CalendarClockIcon,
  CalendarDaysIcon,
  CircleDollarSignIcon,
  UsersIcon,
} from 'lucide-react'
import { useSearchParams } from 'next/navigation'

import { DateFilter } from '@/components/shared/date-filter'
import { DataTable } from '@/components/shared/data-table'
import { KpiCard } from '@/components/shared/kpi-card'
import { PageHeader } from '@/components/shared/page-header'
import { Price } from '@/components/shared/price'
import {
  AppointmentStatusBadge,
  PaymentStatusBadge,
} from '@/components/shared/status-badge'
import { todayKey } from '@/lib/utils/dates'

import { useAdminAppointments, useAdminDashboard } from '@/features/admin/api'

export default function AdminDashboardPage() {
  const searchParams = useSearchParams()
  const date = searchParams.get('date') ?? todayKey()

  const dashboard = useAdminDashboard()
  const appointments = useAdminAppointments({ date })

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Dashboard"
        description="Today at a glance — appointments and revenue."
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label="Today"
          value={dashboard.data?.today_count ?? 0}
          icon={<CalendarDaysIcon className="size-4" />}
          loading={dashboard.isLoading}
        />
        <KpiCard
          label="Upcoming"
          value={dashboard.data?.upcoming_count ?? 0}
          icon={<CalendarClockIcon className="size-4" />}
          loading={dashboard.isLoading}
        />
        <KpiCard
          label="Clients"
          value={dashboard.data?.customer_count ?? 0}
          icon={<UsersIcon className="size-4" />}
          loading={dashboard.isLoading}
        />
        <KpiCard
          label="Revenue today"
          value={
            <Price
              amount={dashboard.data?.revenue_today ?? 0}
              currency={dashboard.data?.currency ?? 'INR'}
            />
          }
          hint={
            dashboard.data
              ? `Month: ${new Intl.NumberFormat('en-IN', {
                  currency: dashboard.data.currency ?? 'INR',
                }).format(dashboard.data.revenue_month)}`
              : undefined
          }
          icon={<CircleDollarSignIcon className="size-4" />}
          loading={dashboard.isLoading}
        />
      </div>

      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold">Appointments</h2>
          <DateFilter defaultValue={todayKey()} />
        </div>

        {appointments.isError ? (
          <QueryError
            error={appointments.error}
            onRetry={() => void appointments.refetch()}
            isRetrying={false}
          />
        ) : (
          <DataTable
            data={appointments.data?.results ?? []}
            keyFor={(row) => row.id}
            loading={appointments.isLoading}
            emptyTitle="No appointments on this day"
            emptyDescription="Try another date to see its schedule."
            columns={[
              {
                header: 'Time',
                cell: (row) => (
                  <span className="whitespace-nowrap font-medium">
                    {format(new Date(row.start_at), 'h:mm a')}
                  </span>
                ),
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
            ]}
          />
        )}
      </section>
    </div>
  )
}
