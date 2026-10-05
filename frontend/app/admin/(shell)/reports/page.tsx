'use client'

import { useSearchParams } from 'next/navigation'

import { RangeSelector } from '@/components/admin/range-selector'
import { KpiCard } from '@/components/shared/kpi-card'
import { PageHeader } from '@/components/shared/page-header'
import { Price } from '@/components/shared/price'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { toApiError } from '@/lib/api/error'
import { addDaysKey, todayKey } from '@/lib/utils/dates'

import { useAppointmentReport, useRevenueReport } from '@/features/admin/api'

export default function AdminReportsPage() {
  const searchParams = useSearchParams()
  const today = todayKey()
  const from = searchParams.get('from') ?? addDaysKey(today, -6)
  const to = searchParams.get('to') ?? today

  const appointments = useAppointmentReport({ from, to })
  const revenue = useRevenueReport({ from, to })

  const byStatus =
    appointments.data && 'by_status' in appointments.data
      ? appointments.data.by_status
      : {}
  const groups =
    appointments.data && 'groups' in appointments.data
      ? appointments.data.groups
      : []
  const totalAppointments =
    appointments.data && 'count' in appointments.data
      ? appointments.data.count
      : groups.reduce((sum, group) => sum + (group.count ?? 0), 0)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Reports"
        description="Appointment volume and revenue for any range."
      />

      <RangeSelector />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <KpiCard
          label="Appointments"
          value={totalAppointments}
          loading={appointments.isLoading}
        />
        <KpiCard
          label="Revenue"
          value={
            <Price
              amount={revenue.data?.total ?? 0}
              currency={revenue.data?.currency ?? 'INR'}
            />
          }
          loading={revenue.isLoading}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Appointments by status</CardTitle>
          </CardHeader>
          <CardContent>
            {appointments.isError ? (
              <p role="alert" className="text-sm text-destructive">
                {toApiError(appointments.error).message}
              </p>
            ) : Object.keys(byStatus).length ? (
              <ul className="flex flex-col gap-2 text-sm">
                {Object.entries(byStatus).map(([status, count]) => (
                  <li
                    key={status}
                    className="flex items-center justify-between gap-3"
                  >
                    <span className="capitalize">
                      {status.replace(/_/g, ' ').toLowerCase()}
                    </span>
                    <span className="font-medium">{count}</span>
                  </li>
                ))}
              </ul>
            ) : groups.length ? (
              <ul className="flex flex-col gap-2 text-sm">
                {groups.map((group, index) => (
                  <li
                    key={group.status ?? index}
                    className="flex items-center justify-between gap-3"
                  >
                    <span className="capitalize">
                      {group.status?.replace(/_/g, ' ').toLowerCase() ?? '—'}
                    </span>
                    <span className="font-medium">{group.count}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                No appointments in this range.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Revenue series</CardTitle>
          </CardHeader>
          <CardContent>
            {revenue.isError ? (
              <p role="alert" className="text-sm text-destructive">
                {toApiError(revenue.error).message}
              </p>
            ) : revenue.data?.series.length ? (
              <ul className="flex flex-col gap-2 text-sm">
                {revenue.data.series.map((point, index) => (
                  <li
                    key={point.period ?? point.date ?? index}
                    className="flex items-center justify-between gap-3"
                  >
                    <span className="text-muted-foreground">
                      {point.period ?? point.date ?? '—'}
                    </span>
                    <span className="font-medium">
                      <Price
                        amount={point.amount}
                        currency={revenue.data?.currency ?? 'INR'}
                      />
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                No revenue recorded in this range.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
