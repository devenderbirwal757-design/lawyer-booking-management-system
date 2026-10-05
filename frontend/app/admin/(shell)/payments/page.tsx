'use client'

import { format } from 'date-fns'
import { QueryError } from '@/components/shared/query-error'
import Link from 'next/link'
import { useUrlFilters } from '@/lib/hooks/use-url-filters'

import { DataTable } from '@/components/shared/data-table'
import { PageHeader } from '@/components/shared/page-header'
import { Price } from '@/components/shared/price'
import { PaymentStatusBadge } from '@/components/shared/status-badge'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { addDaysKey, todayKey } from '@/lib/utils/dates'
import { PAYMENT_STATUS_LABELS } from '@/components/shared/status-badge'

import { useAdminPayments } from '@/features/admin/api'

export default function AdminPaymentsPage() {
  const { values, set } = useUrlFilters({
    status: '',
    from: addDaysKey(todayKey(), -29),
    to: todayKey(),
  })

  const payments = useAdminPayments({
    status: values.status || undefined,
    from: values.from || undefined,
    to: values.to || undefined,
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Payments"
        description="Every payment and refund for the practice."
      />

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium" htmlFor="payment-status">
            Status
          </label>
          <Select
            value={values.status || 'all'}
            onValueChange={(value) =>
              set('status', value === 'all' ? '' : value)
            }
          >
            <SelectTrigger id="payment-status" className="h-9 w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {Object.entries(PAYMENT_STATUS_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium" htmlFor="payment-from">
            From
          </label>
          <Input
            id="payment-from"
            type="date"
            value={values.from}
            onChange={(e) => set('from', e.target.value)}
            className="h-9 w-40"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium" htmlFor="payment-to">
            To
          </label>
          <Input
            id="payment-to"
            type="date"
            value={values.to}
            onChange={(e) => set('to', e.target.value)}
            className="h-9 w-40"
          />
        </div>
      </div>

      {payments.isError ? (
        <QueryError
          error={payments.error}
          onRetry={() => void payments.refetch()}
          isRetrying={false}
        />
      ) : (
        <DataTable
          data={payments.data?.results ?? []}
          keyFor={(row) => row.id}
          loading={payments.isLoading}
          emptyTitle="No payments in this range"
          emptyDescription="Widen the date range or clear the status filter."
          columns={[
            {
              header: 'Date',
              cell: (row) =>
                row.created_at ? (
                  <Link
                    href={`/admin/payments/${row.id}`}
                    className="whitespace-nowrap font-medium hover:underline"
                  >
                    {format(new Date(row.created_at), 'd MMM yyyy, h:mm a')}
                  </Link>
                ) : (
                  '—'
                ),
            },
            {
              header: 'Client',
              cell: (row) => (
                <span>{row.customer?.name ?? row.customer?.phone ?? '—'}</span>
              ),
            },
            {
              header: 'Amount',
              cell: (row) => (
                <Price amount={row.amount} currency={row.currency} />
              ),
            },
            {
              header: 'Status',
              cell: (row) => <PaymentStatusBadge status={row.status} />,
            },
            {
              header: 'Gateway payment',
              cell: (row) => (
                <span className="font-mono text-xs text-muted-foreground">
                  {row.gateway_payment_id ?? '—'}
                </span>
              ),
            },
          ]}
        />
      )}
    </div>
  )
}
