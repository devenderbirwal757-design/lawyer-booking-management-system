'use client'

import { format } from 'date-fns'
import { AlertCircleIcon, FileTextIcon, ReceiptTextIcon } from 'lucide-react'
import Link from 'next/link'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/empty-state'
import { Price } from '@/components/shared/price'
import { PaymentStatusBadge } from '@/components/shared/status-badge'
import { API_BASE_URL } from '@/lib/api/client'
import { toApiError } from '@/lib/api/error'

import { useMePayments } from '@/features/portal/api'

export default function PaymentsPage() {
  const payments = useMePayments()

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="font-serif text-2xl font-semibold tracking-tight">
          Payments
        </h1>
        <p className="text-sm text-muted-foreground">
          Every payment made on your account.
        </p>
      </div>

      {payments.isLoading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-12 rounded-lg" />
          ))}
        </div>
      ) : payments.isError ? (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Could not load your payments</AlertTitle>
          <AlertDescription>
            {toApiError(payments.error).message}
          </AlertDescription>
        </Alert>
      ) : !payments.data?.results.length ? (
        <EmptyState
          icon={<ReceiptTextIcon className="size-6" />}
          title="No payments yet"
          description="Payments for confirmed consultations will appear here."
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Booking</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Receipt</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {payments.data.results.map((payment) => (
                <TableRow key={payment.id}>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {format(
                      new Date(
                        payment.paid_at ?? payment.created_at ?? payment.id
                      ),
                      'd MMM yyyy, h:mm a'
                    )}
                  </TableCell>
                  <TableCell>
                    {payment.appointment_id ? (
                      <Link
                        href={`/bookings/${payment.appointment_id}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {payment.appointment_id.slice(0, 8)}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Price
                      amount={payment.amount}
                      currency={payment.currency}
                    />
                  </TableCell>
                  <TableCell>
                    <PaymentStatusBadge status={payment.status} />
                  </TableCell>
                  <TableCell className="text-right">
                    <a
                      href={`${API_BASE_URL}/payments/${payment.order_id ?? payment.id}/receipt`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                    >
                      <FileTextIcon className="size-3.5" />
                      View
                    </a>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
