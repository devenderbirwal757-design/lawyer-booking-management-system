'use client'

import { format } from 'date-fns'
import { QueryError } from '@/components/shared/query-error'
import { ArrowLeftIcon } from 'lucide-react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { DataTable } from '@/components/shared/data-table'
import { PageHeader } from '@/components/shared/page-header'
import { Price } from '@/components/shared/price'
import {
  AppointmentStatusBadge,
  PaymentStatusBadge,
} from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'

import {
  useAdminAppointments,
  useAdminCustomer,
  useAdminPayments,
  useUpdateClientNotes,
} from '@/features/admin/api'

export default function AdminClientDetailPage() {
  const { id } = useParams<{ id: string }>()
  const customer = useAdminCustomer(id)
  const appointments = useAdminAppointments({ customer_id: id })
  const payments = useAdminPayments({ customer_id: id })
  const updateNotes = useUpdateClientNotes()

  const [notes, setNotes] = useState('')
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    if (customer.data?.notes !== undefined && !dirty) {
      setNotes(customer.data.notes ?? '')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customer.data?.notes])

  const saveNotes = () => {
    updateNotes.mutate(
      { id, notes },
      {
        onSuccess: () => {
          setDirty(false)
          toast.success('Notes saved')
        },
        onError: () => toast.error('Could not save notes'),
      }
    )
  }

  const profile = customer.data

  return (
    <div className="flex flex-col gap-6">
      <Button variant="ghost" size="sm" asChild className="-mx-3 w-fit">
        <Link href="/admin/clients">
          <ArrowLeftIcon className="size-4" /> Clients
        </Link>
      </Button>

      <PageHeader
        title={profile?.name ?? 'Client'}
        description={
          profile
            ? `Client since ${format(new Date(profile.created_at ?? Date.now()), 'MMMM yyyy')}`
            : 'Loading…'
        }
      />

      {customer.isError ? (
        <QueryError
          error={customer.error}
          onRetry={() => void customer.refetch()}
          isRetrying={false}
        />
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Contact</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            {!profile ? (
              <Skeleton className="h-16 w-full" />
            ) : (
              <>
                <Row label="Phone">{profile.phone ?? '—'}</Row>
                <Row label="Email">{profile.email ?? '—'}</Row>
                <Row label="Appointments">
                  {profile.appointment_count ?? '—'}
                </Row>
              </>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-sm">Notes</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Textarea
              value={notes}
              onChange={(e) => {
                setNotes(e.target.value)
                setDirty(true)
              }}
              placeholder="Add notes about this client…"
              className="min-h-32"
              aria-label="Client notes"
            />
            <div className="flex justify-end">
              <Button
                size="sm"
                disabled={!dirty || updateNotes.isPending}
                onClick={saveNotes}
              >
                {updateNotes.isPending ? 'Saving…' : 'Save notes'}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Appointments</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            data={appointments.data?.results ?? []}
            keyFor={(row) => row.id}
            loading={appointments.isLoading}
            emptyTitle="No appointments yet"
            columns={[
              {
                header: 'Date & time',
                cell: (row) => (
                  <Link
                    href={`/admin/appointments/${row.id}`}
                    className="whitespace-nowrap font-medium hover:underline"
                  >
                    {format(new Date(row.start_at), 'd MMM yyyy, h:mm a')}
                  </Link>
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Payment history</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            data={payments.data?.results ?? []}
            keyFor={(row) => row.id}
            loading={payments.isLoading}
            emptyTitle="No payments recorded"
            columns={[
              {
                header: 'Date',
                cell: (row) => (
                  <span className="whitespace-nowrap">
                    {row.created_at
                      ? format(new Date(row.created_at), 'd MMM yyyy')
                      : '—'}
                  </span>
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
            ]}
          />
        </CardContent>
      </Card>
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
