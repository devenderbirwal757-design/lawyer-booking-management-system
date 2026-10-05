'use client'

import { format } from 'date-fns'
import { QueryError } from '@/components/shared/query-error'
import { ArrowLeftIcon } from 'lucide-react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useState } from 'react'
import { toast } from 'sonner'

import { RefundDialog } from '@/components/admin/refund-dialog'
import { DataTable } from '@/components/shared/data-table'
import { PageHeader } from '@/components/shared/page-header'
import { Price } from '@/components/shared/price'
import { PaymentStatusBadge } from '@/components/shared/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

import {
  useAdminPayment,
  useAdminRefunds,
  useSettleRefund,
} from '@/features/admin/api'

export default function AdminPaymentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const payment = useAdminPayment(id)
  const refunds = useAdminRefunds({})
  const settle = useSettleRefund()
  const [refundOpen, setRefundOpen] = useState(false)

  const row = payment.data
  const related = (refunds.data?.results ?? []).filter(
    (refund) => refund.payment?.id === id
  )
  const canRefund = row?.status === 'SUCCESS' && related.length === 0

  return (
    <div className="flex flex-col gap-6">
      <Button variant="ghost" size="sm" asChild className="-mx-3 w-fit">
        <Link href="/admin/payments">
          <ArrowLeftIcon className="size-4" /> Payments
        </Link>
      </Button>

      <PageHeader
        title={row ? `Payment ${row.id.slice(0, 8)}` : 'Payment'}
        description={row ? 'Gateway details and refund history.' : 'Loading…'}
        actions={
          canRefund ? (
            <Button onClick={() => setRefundOpen(true)}>Refund</Button>
          ) : null
        }
      />

      {payment.isError ? (
        <QueryError
          error={payment.error}
          onRetry={() => void payment.refetch()}
          isRetrying={false}
        />
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Details</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            {!row ? (
              <Skeleton className="h-24 w-full" />
            ) : (
              <>
                <Row label="Amount">
                  <Price amount={row.amount} currency={row.currency} />
                </Row>
                <Row label="Status">
                  <PaymentStatusBadge status={row.status} />
                </Row>
                <Row label="Client">
                  {row.customer?.name ?? row.customer?.phone ?? '—'}
                </Row>
                <Row label="Created">
                  {row.created_at
                    ? format(new Date(row.created_at), 'd MMM yyyy, h:mm a')
                    : '—'}
                </Row>
                <Row label="Paid">
                  {row.paid_at
                    ? format(new Date(row.paid_at), 'd MMM yyyy, h:mm a')
                    : '—'}
                </Row>
                <Row label="Order ID">
                  <span className="font-mono text-xs">
                    {row.gateway_order_id ?? row.order_id ?? '—'}
                  </span>
                </Row>
                <Row label="Payment ID">
                  <span className="font-mono text-xs">
                    {row.gateway_payment_id ?? '—'}
                  </span>
                </Row>
                {row.appointment_id ? (
                  <Row label="Appointment">
                    <Link
                      href={`/admin/appointments/${row.appointment_id}`}
                      className="font-medium hover:underline"
                    >
                      View appointment
                    </Link>
                  </Row>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Refunds</CardTitle>
          </CardHeader>
          <CardContent>
            <DataTable
              data={related}
              keyFor={(item) => item.id}
              loading={refunds.isLoading}
              emptyTitle="No refunds"
              emptyDescription="Refunds you queue will appear here."
              columns={[
                {
                  header: 'Amount',
                  cell: (item) => (
                    <Price amount={item.amount} currency={item.currency} />
                  ),
                },
                {
                  header: 'Status',
                  cell: (item) => (
                    <Badge
                      variant={
                        item.status === 'SUCCEEDED' ? 'default' : 'secondary'
                      }
                    >
                      {item.status.replace('_', ' ')}
                    </Badge>
                  ),
                },
                {
                  header: 'Reason',
                  cell: (item) => (
                    <span className="text-muted-foreground">
                      {item.reason ?? '—'}
                    </span>
                  ),
                },
                {
                  header: <span className="sr-only">Actions</span>,
                  cell: (item) =>
                    item.status === 'PENDING_ACTION' ? (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={settle.isPending}
                        onClick={() =>
                          settle.mutate(item.id, {
                            onSuccess: () => toast.success('Refund settled'),
                            onError: () =>
                              toast.error('Could not settle the refund'),
                          })
                        }
                      >
                        Settle
                      </Button>
                    ) : null,
                  className: 'text-right',
                },
              ]}
            />
          </CardContent>
        </Card>
      </div>

      {row ? (
        <RefundDialog
          paymentId={row.id}
          amount={row.amount}
          currency={row.currency}
          open={refundOpen}
          onOpenChange={setRefundOpen}
        />
      ) : null}
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
